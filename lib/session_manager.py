"""
NotebookLM Session Manager
Persistent session handling with storage reuse and command execution
"""

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict

from .rate_limiter import RateLimiter, detect_rate_limit, RateLimitError


class NotebookLMSession:
    """
    Manages a persistent NotebookLM session for a client
    Eliminates storage file thrashing by reusing auth state
    """

    def __init__(
        self,
        client_id: str,
        shared_auth_path: Path,
        storage_dir: Path,
        rate_limiter: RateLimiter
    ):
        """
        Args:
            client_id: Unique client identifier
            shared_auth_path: Path to shared authentication state
            storage_dir: Directory for storage files
            rate_limiter: Rate limiter instance
        """
        self.client_id = client_id
        self.storage_path = storage_dir / f".storage_{client_id}.json"
        self.notebook_id: Optional[str] = None
        self._initialized = False
        self.rate_limiter = rate_limiter

        # Copy shared auth once during initialization
        if shared_auth_path.exists():
            self.storage_path.write_text(shared_auth_path.read_text())
            logging.debug(f"[{client_id}] Auth state copied to {self.storage_path}")
        else:
            logging.warning(f"[{client_id}] Shared auth path not found: {shared_auth_path}")

    async def initialize(self) -> None:
        """Initialize session - refresh auth once per session"""
        if self._initialized:
            return

        logging.info(f"[{self.client_id}] Initializing session")

        try:
            await self._run_cmd([
                "notebooklm",
                "--storage", str(self.storage_path),
                "auth", "refresh", "--quiet"
            ])
            self._initialized = True
            logging.info(f"[{self.client_id}] Session initialized successfully")

        except Exception as e:
            logging.error(f"[{self.client_id}] Session initialization failed: {e}")
            raise

    async def _run_cmd(
        self,
        cmd: list,
        input_data: Optional[str] = None,
        timeout: int = 300
    ) -> Tuple[str, str]:
        """
        Execute NotebookLM command with rate limiting

        Args:
            cmd: Command list
            input_data: Optional stdin data
            timeout: Command timeout in seconds

        Returns:
            Tuple of (stdout, stderr)

        Raises:
            RateLimitError: If rate limit detected
            subprocess.CalledProcessError: If command fails
        """
        # Acquire rate limit token
        await self.rate_limiter.acquire()

        logging.debug(f"[{self.client_id}] Executing: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Run with timeout
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input_data.encode() if input_data else None),
                timeout=timeout
            )

            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')

            # Check for rate limiting
            if detect_rate_limit(stdout_str, stderr_str):
                logging.warning(f"[{self.client_id}] Rate limit detected")
                raise RateLimitError(f"Rate limit detected: {stderr_str[:200]}")

            # Check for command failure
            if proc.returncode != 0:
                logging.error(
                    f"[{self.client_id}] Command failed (exit {proc.returncode}): "
                    f"{stderr_str[:200]}"
                )
                raise subprocess.CalledProcessError(
                    proc.returncode,
                    cmd,
                    stdout_str,
                    stderr_str
                )

            return stdout_str, stderr_str

        except asyncio.TimeoutError:
            logging.error(f"[{self.client_id}] Command timeout after {timeout}s")
            proc.kill()
            raise

    async def get_or_create_notebook(self, name: str) -> str:
        """
        Get existing notebook or create new one (idempotent)

        Args:
            name: Notebook name

        Returns:
            Notebook UUID

        Raises:
            Exception: If notebook creation fails
        """
        if self.notebook_id:
            return self.notebook_id

        logging.info(f"[{self.client_id}] Getting or creating notebook: {name}")

        # Check cache first
        cache = await self._fetch_notebook_cache()
        normalized = re.sub(r'[^a-zA-Z0-9]', '', name).lower().strip()

        if normalized in cache:
            self.notebook_id = cache[normalized]
            logging.info(f"[{self.client_id}] Found existing notebook: {self.notebook_id}")
            return self.notebook_id

        # Create new notebook
        logging.info(f"[{self.client_id}] Creating new notebook: {name}")
        stdout, stderr = await self._run_cmd([
            "notebooklm",
            "--storage", str(self.storage_path),
            "create",
            name
        ])

        # Extract UUID from response
        match = re.search(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', stdout, re.IGNORECASE)
        if match:
            self.notebook_id = match.group(1)
            logging.info(f"[{self.client_id}] Created notebook: {self.notebook_id}")
            return self.notebook_id

        # Retry cache lookup (eventual consistency)
        logging.warning(f"[{self.client_id}] UUID not in create response, rechecking cache")
        await asyncio.sleep(2.0)
        cache = await self._fetch_notebook_cache()

        if normalized in cache:
            self.notebook_id = cache[normalized]
            logging.info(f"[{self.client_id}] Found in cache after retry: {self.notebook_id}")
            return self.notebook_id

        raise Exception(f"Failed to create/find notebook: {name}")

    async def _fetch_notebook_cache(self) -> Dict[str, str]:
        """
        Fetch and parse notebook list

        Returns:
            Dict mapping normalized names to UUIDs
        """
        try:
            stdout, stderr = await self._run_cmd([
                "notebooklm",
                "--storage", str(self.storage_path),
                "list"
            ])

            cache = {}
            uuid_pattern = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)

            for line in stdout.splitlines():
                match = uuid_pattern.search(line)
                if match:
                    nb_uuid = match.group(1)

                    # Normalize the line for matching
                    clean_name = line.replace(nb_uuid, "")
                    clean_name = re.sub(r'│|┃|║|─|═|-|_|:|\+', ' ', clean_name)
                    clean_name = re.sub(
                        r'\b(ready|processing|waiting|status|uuid|title|created|owner)\b',
                        ' ',
                        clean_name,
                        flags=re.IGNORECASE
                    )
                    clean_name = re.sub(r'[^\x00-\x7F]+', ' ', clean_name)
                    clean_name = re.sub(r'\d{4}-\d{2}-\d{2}|\d{2}:\d{2}', ' ', clean_name)

                    normalized_key = re.sub(r'[^a-zA-Z0-9]', '', clean_name).lower().strip()
                    if normalized_key:
                        cache[normalized_key] = nb_uuid

            logging.debug(f"[{self.client_id}] Cached {len(cache)} notebooks")
            return cache

        except Exception as e:
            logging.error(f"[{self.client_id}] Failed to fetch notebook cache: {e}")
            return {}

    async def use_notebook(self, notebook_id: Optional[str] = None) -> None:
        """
        Set active notebook context

        Args:
            notebook_id: Notebook UUID (uses self.notebook_id if not provided)
        """
        nb_id = notebook_id or self.notebook_id
        if not nb_id:
            raise ValueError("No notebook ID available")

        await self._run_cmd([
            "notebooklm",
            "--storage", str(self.storage_path),
            "use",
            nb_id
        ])

        logging.debug(f"[{self.client_id}] Using notebook: {nb_id}")

    async def add_source(
        self,
        source_path: str,
        title: Optional[str] = None
    ) -> None:
        """
        Add source file to notebook

        Args:
            source_path: Path to source file or URL
            title: Optional source title
        """
        cmd = [
            "notebooklm",
            "--storage", str(self.storage_path),
            "source", "add"
        ]

        if title:
            cmd.extend(["--title", title])

        cmd.append(source_path)

        await self._run_cmd(cmd)
        logging.info(f"[{self.client_id}] Added source: {title or source_path}")

    async def add_research(
        self,
        prompt_file: Path,
        mode: str = "deep"
    ) -> Tuple[str, str]:
        """
        Add research note from prompt file

        Args:
            prompt_file: Path to prompt file
            mode: Research mode ('deep' or 'fast')

        Returns:
            Tuple of (stdout, stderr)
        """
        stdout, stderr = await self._run_cmd([
            "notebooklm",
            "--storage", str(self.storage_path),
            "source", "add-research",
            "--prompt-file", str(prompt_file),
            "--mode", mode,
            "--no-wait"
        ])

        logging.info(f"[{self.client_id}] Added research from: {prompt_file.name}")
        return stdout, stderr

    async def ask_question(
        self,
        prompt_file: Path,
        save_as_note: bool = True
    ) -> str:
        """
        Ask question and optionally save as note

        Args:
            prompt_file: Path to prompt file
            save_as_note: Save response as note

        Returns:
            Response text
        """
        cmd = [
            "notebooklm",
            "--storage", str(self.storage_path),
            "ask",
            "--prompt-file", str(prompt_file)
        ]

        if save_as_note:
            cmd.append("--save-as-note")

        stdout, stderr = await self._run_cmd(cmd)
        logging.info(f"[{self.client_id}] Asked question from: {prompt_file.name}")
        return stdout

    async def list_notes(self) -> str:
        """
        List all notes in notebook

        Returns:
            Notes list output
        """
        stdout, stderr = await self._run_cmd([
            "notebooklm",
            "--storage", str(self.storage_path),
            "note", "list"
        ])
        return stdout

    async def view_note(self, note_id: str) -> str:
        """
        View note content

        Args:
            note_id: Note UUID

        Returns:
            Note content
        """
        stdout, stderr = await self._run_cmd([
            "notebooklm",
            "--storage", str(self.storage_path),
            "note", "view",
            note_id
        ])
        return stdout

    async def generate_document(
        self,
        title: str,
        content: str
    ) -> str:
        """
        Generate Google Doc

        Args:
            title: Document title
            content: HTML/text content

        Returns:
            Document URL or output
        """
        stdout, stderr = await self._run_cmd(
            [
                "notebooklm",
                "--storage", str(self.storage_path),
                "generate", "document",
                title
            ],
            input_data=content
        )

        logging.info(f"[{self.client_id}] Generated document: {title}")
        return stdout

    async def generate_asset(self, asset_type: str) -> None:
        """
        Generate asset (mind-map, slide-deck, etc.)

        Args:
            asset_type: Type of asset to generate
        """
        await self._run_cmd([
            "notebooklm",
            "--storage", str(self.storage_path),
            "generate",
            asset_type
        ])

        logging.info(f"[{self.client_id}] Generated {asset_type}")

    def cleanup(self) -> None:
        """Cleanup session storage file"""
        try:
            if self.storage_path.exists():
                self.storage_path.unlink()
                logging.debug(f"[{self.client_id}] Cleaned up storage file")
        except Exception as e:
            logging.warning(f"[{self.client_id}] Cleanup failed: {e}")
