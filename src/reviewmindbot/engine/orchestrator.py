"""Coordinates a full review: route -> chunk -> review -> aggregate.

This is the module the README always claimed existed. Previously the CLI
hand-rolled the same flow inline and the Orchestrator was dead code.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.chunking import Chunk, build_chunks
from ..core.diff_parser import FileChange
from ..errors import ProviderError
from ..usage import BudgetExceeded
from .aggregator import Aggregator
from .file_router import FileRouter
from .models import ReviewResult
from .reviewer import Reviewer

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        reviewer: Reviewer,
        router: FileRouter | None = None,
        aggregator: Aggregator | None = None,
        *,
        max_chunk_size: int = 12000,
        chunk_overlap: int = 400,
        max_concurrency: int = 4,
    ) -> None:
        self.reviewer = reviewer
        self.router = router or FileRouter()
        self.aggregator = aggregator or Aggregator()
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_concurrency = max(1, max_concurrency)

    def review(self, files: list[FileChange]) -> ReviewResult:
        selected = self.router.select(files)
        skipped = len(files) - len(selected)
        if skipped:
            logger.info("Skipped %d file(s): binary, deleted or ignored", skipped)

        chunks = build_chunks(selected, self.max_chunk_size, self.chunk_overlap)
        logger.info(
            "Reviewing %d file(s) in %d chunk(s)", len(selected), len(chunks)
        )

        batches, failures, skipped = self._review_chunks(chunks)

        return ReviewResult(
            findings=self.aggregator.aggregate(batches),
            files_reviewed=len(selected),
            chunks_reviewed=len(chunks) - failures - skipped,
            failed_chunks=failures,
            skipped_chunks=skipped,
            budget_exhausted=skipped > 0,
            usage=self.reviewer.llm.usage.to_dict(),
        )

    def _review_chunks(self, chunks: list[Chunk]) -> tuple[list[list], int, int]:
        """Review chunks in parallel, tolerating individual failures.

        One chunk failing must not discard the findings from the other forty --
        the previous sequential loop aborted the whole run on any provider error.
        """
        if not chunks:
            return [], 0, 0

        batches: list[list] = []
        failures = 0
        skipped = 0

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            futures = {
                pool.submit(self.reviewer.review, chunk): index
                for index, chunk in enumerate(chunks, start=1)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    batches.append(future.result())
                except BudgetExceeded as exc:
                    # Expected once the ceiling is reached: report partial
                    # results rather than failing a PR over a spend limit.
                    skipped += 1
                    if skipped == 1:
                        logger.warning("%s Remaining chunks will be skipped.", exc)
                except ProviderError as exc:
                    failures += 1
                    logger.error("Chunk %d/%d failed: %s", index, len(chunks), exc)

        if failures and failures == len(chunks):
            raise ProviderError(
                f"All {len(chunks)} review request(s) failed. "
                "Check your API key, model name and network connection."
            )

        return batches, failures, skipped
