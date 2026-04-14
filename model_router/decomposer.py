"""Task decomposer -- splits large tasks into routable subtasks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from model_router.models import TaskFeatures, TaskRequest, TaskType
from model_router.registry import ModelCapabilities, ModelRegistry


@dataclass
class Subtask:
    index: int
    prompt: str
    task_type: TaskType
    model_hint: str | None = None       # force a specific model for this subtask
    context_from: list[int] = field(default_factory=list)  # prior subtask indices to prepend


class TaskDecomposer:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def should_decompose(self, features: TaskFeatures, model: ModelCapabilities) -> bool:
        threshold = self._registry.routing.decompose_threshold
        return features.estimated_tokens > model.context_tokens * threshold

    def estimate_subtask_count(self, features: TaskFeatures, model: ModelCapabilities) -> int:
        ratio = features.estimated_tokens / (model.context_tokens * 0.6)
        return max(2, min(int(ratio) + 1, 8))

    def decompose(self, request: TaskRequest, features: TaskFeatures) -> list[Subtask]:
        """Choose decomposition strategy based on task type."""
        strategy_map = {
            TaskType.CODING:    self._decompose_coding,
            TaskType.REVIEW:    self._decompose_review,
            TaskType.DOCS:      self._decompose_docs,
            TaskType.REASONING: self._decompose_reasoning,
            TaskType.CHAT:      self._decompose_simple,
        }
        fn = strategy_map.get(features.task_type, self._decompose_simple)
        return fn(request, features)

    def combine(self, subtask_results: list[str], strategy: str = "sequential") -> str:
        """
        Merge subtask outputs.
        - sequential: concatenate with headers
        - synthesis: feed all outputs to a compact summary call (handled by router)
        """
        if strategy == "sequential":
            parts = []
            for i, result in enumerate(subtask_results, 1):
                parts.append(f"## Part {i}\n\n{result}")
            return "\n\n---\n\n".join(parts)
        # synthesis strategy signals the router to do an extra LLM merge call
        return "\n\n".join(subtask_results)

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _decompose_coding(request: TaskRequest, features: TaskFeatures) -> list[Subtask]:
        """Split by file/module boundaries mentioned in the prompt."""
        path_pattern = re.compile(r"[\w./\\-]+\.\w{2,5}")
        files = list(dict.fromkeys(path_pattern.findall(request.prompt)))  # dedup, preserve order

        if len(files) >= 2:
            subtasks = []
            for i, filepath in enumerate(files):
                subtasks.append(Subtask(
                    index=i,
                    prompt=(
                        f"Focus only on `{filepath}`.\n\n"
                        f"Original task:\n{request.prompt}\n\n"
                        "Implement only the changes relevant to this file."
                    ),
                    task_type=TaskType.CODING,
                    model_hint="claude-sonnet-4-6",
                ))
            # Final integration subtask uses Opus
            subtasks.append(Subtask(
                index=len(files),
                prompt=(
                    "Review and integrate all the individual file implementations above "
                    "into a coherent solution. Fix any cross-file inconsistencies."
                ),
                task_type=TaskType.REVIEW,
                model_hint="claude-opus-4-6",
                context_from=list(range(len(files))),
            ))
            return subtasks

        # Fallback: split by chunk size
        return TaskDecomposer._decompose_simple(request, features)

    @staticmethod
    def _decompose_review(request: TaskRequest, _: TaskFeatures) -> list[Subtask]:
        """Split by review concern: security, performance, style, correctness."""
        concerns = [
            ("Security", "Focus on security vulnerabilities, injection risks, auth issues, secrets exposure."),
            ("Performance", "Focus on performance bottlenecks, O(n) complexity, database queries, caching."),
            ("Correctness", "Focus on logic bugs, edge cases, error handling, off-by-one errors."),
            ("Style & Maintainability", "Focus on code clarity, naming, structure, duplication, and documentation."),
        ]
        subtasks = []
        for i, (concern, instruction) in enumerate(concerns):
            subtasks.append(Subtask(
                index=i,
                prompt=(
                    f"## Review focus: {concern}\n\n{instruction}\n\n"
                    f"Code to review:\n{request.prompt}"
                ),
                task_type=TaskType.REVIEW,
                model_hint="claude-sonnet-4-6",
            ))
        # Summary subtask
        subtasks.append(Subtask(
            index=len(concerns),
            prompt=(
                "Synthesize the review findings above into a prioritised list of "
                "actionable recommendations, from critical to minor."
            ),
            task_type=TaskType.REVIEW,
            model_hint="claude-opus-4-6",
            context_from=list(range(len(concerns))),
        ))
        return subtasks

    @staticmethod
    def _decompose_docs(request: TaskRequest, _: TaskFeatures) -> list[Subtask]:
        """Split documentation into: overview, API reference, examples."""
        sections = [
            ("Overview & Architecture",
             "Write the project overview, key concepts, and high-level architecture section."),
            ("API Reference",
             "Write the complete API reference including all public functions, classes, and parameters."),
            ("Examples & Guides",
             "Write usage examples and step-by-step guides for the most common workflows."),
        ]
        subtasks = []
        for i, (section, instruction) in enumerate(sections):
            subtasks.append(Subtask(
                index=i,
                prompt=f"## Documentation section: {section}\n\n{instruction}\n\nContext:\n{request.prompt}",
                task_type=TaskType.DOCS,
                model_hint="claude-sonnet-4-6",
            ))
        subtasks.append(Subtask(
            index=len(sections),
            prompt=(
                "Assemble the documentation sections above into a single coherent document. "
                "Add a table of contents, smooth transitions, and ensure consistent terminology."
            ),
            task_type=TaskType.DOCS,
            model_hint="claude-opus-4-6",
            context_from=list(range(len(sections))),
        ))
        return subtasks

    @staticmethod
    def _decompose_reasoning(request: TaskRequest, _: TaskFeatures) -> list[Subtask]:
        """
        Three-stage chain: analyse -> analyse -> synthesise.
        Cheaper models do analysis; Opus synthesises.
        """
        half = len(request.prompt) // 2
        part_a = request.prompt[:half]
        part_b = request.prompt[half:]
        return [
            Subtask(
                index=0,
                prompt=f"Analyse the following information (Part 1 of 2):\n\n{part_a}",
                task_type=TaskType.REASONING,
                model_hint="claude-sonnet-4-6",
            ),
            Subtask(
                index=1,
                prompt=f"Analyse the following information (Part 2 of 2):\n\n{part_b}",
                task_type=TaskType.REASONING,
                model_hint="claude-sonnet-4-6",
            ),
            Subtask(
                index=2,
                prompt=(
                    "Using the analyses above, synthesise a final, comprehensive answer "
                    "to the original question:\n\n" + request.prompt[:500] + "..."
                ),
                task_type=TaskType.REASONING,
                model_hint="claude-opus-4-6",
                context_from=[0, 1],
            ),
        ]

    @staticmethod
    def _decompose_simple(request: TaskRequest, features: TaskFeatures) -> list[Subtask]:
        """Generic chunk-based split for tasks with no structural signals."""
        chunk_size = max(2000, len(request.prompt) // 3)
        chunks = [request.prompt[i:i + chunk_size]
                  for i in range(0, len(request.prompt), chunk_size)]
        subtasks = [
            Subtask(
                index=i,
                prompt=f"Process this section (part {i + 1} of {len(chunks)}):\n\n{chunk}",
                task_type=features.task_type,
                model_hint="claude-sonnet-4-6",
            )
            for i, chunk in enumerate(chunks)
        ]
        if len(subtasks) > 1:
            subtasks.append(Subtask(
                index=len(chunks),
                prompt="Combine the outputs from all parts above into a single coherent result.",
                task_type=features.task_type,
                model_hint="claude-sonnet-4-6",
                context_from=list(range(len(chunks))),
            ))
        return subtasks
