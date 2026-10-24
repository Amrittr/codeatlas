"""Project-level statistics, computed only from scanned nodes."""

from __future__ import annotations

from collections import defaultdict

from app.analyzers.config_detector import detect_config
from app.schemas.project import (
    Classification,
    ClassificationStat,
    ConfigFileStat,
    ExtensionStat,
    FileRef,
    LanguageStat,
    GeneratedFolderStat,
    ProjectStats,
)
from app.services.nodes import DirectoryRecord, FileRecord

NO_EXTENSION = "(none)"
MAX_LISTED_FILES = 10
MAX_LISTED_CONFIG_FILES = 100


MAX_LISTED_GENERATED_FOLDERS = 100


def compute_statistics(
    nodes: dict[str, FileRecord | DirectoryRecord],
    root_id: str,
    *,
    excluded_entry_count: int = 0,
    generated_folders=(),
) -> ProjectStats:
    """Statistics over analyzed nodes only. Excluded files and folders are counted separately."""
    all_files = [node for node in nodes.values() if isinstance(node, FileRecord)]
    all_directories = [node for node in nodes.values() if isinstance(node, DirectoryRecord) and node.id != root_id]
    files = [node for node in all_files if not node.excluded]
    directories = [node for node in all_directories if not node.excluded]

    by_extension: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_language: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_classification: dict[Classification, list[int]] = defaultdict(lambda: [0, 0])
    config_files: list[ConfigFileStat] = []

    for file in files:
        buckets = [by_extension[file.extension or NO_EXTENSION], by_classification[file.classification]]
        if file.language:
            buckets.append(by_language[file.language])
        for bucket in buckets:
            bucket[0] += 1
            bucket[1] += file.size_bytes
        match = detect_config(file.name, file.path)
        if match is not None and len(config_files) < MAX_LISTED_CONFIG_FILES:
            config_files.append(ConfigFileStat(node_id=file.id, path=file.path, label=match.label, category=match.category))

    def ranked(counter: dict) -> list[tuple]:
        return sorted(counter.items(), key=lambda item: (-item[1][0], -item[1][1], str(item[0])))

    largest = sorted(files, key=lambda file: (-file.size_bytes, file.path))[:MAX_LISTED_FILES]
    config_files.sort(key=lambda item: (item.path.count("/"), item.path))

    return ProjectStats(
        total_files=len(files),
        total_directories=len(directories),
        total_size_bytes=sum(file.size_bytes for file in files),
        file_type_count=len(by_extension),
        source_file_count=by_classification[Classification.SOURCE][0],
        test_file_count=by_classification[Classification.TEST][0],
        config_file_count=by_classification[Classification.CONFIG][0],
        documentation_file_count=by_classification[Classification.DOCUMENTATION][0],
        hidden_file_count=sum(1 for file in files if file.hidden),
        empty_directory_count=sum(1 for node in directories if node.child_count == 0),
        excluded_file_count=len(all_files) - len(files),
        excluded_directory_count=len(all_directories) - len(directories),
        excluded_entry_count=excluded_entry_count,
        max_depth=max((node.depth for node in (*files, *directories)), default=0),
        extensions=[ExtensionStat(extension=ext, file_count=c, size_bytes=s) for ext, (c, s) in ranked(by_extension)],
        languages=[LanguageStat(language=lang, file_count=c, size_bytes=s) for lang, (c, s) in ranked(by_language)],
        classifications=[
            ClassificationStat(classification=cls, file_count=c, size_bytes=s)
            for cls, (c, s) in ranked(by_classification)
            if c
        ],
        largest_files=[FileRef(node_id=file.id, path=file.path, size_bytes=file.size_bytes) for file in largest],
        config_files=config_files,
        generated_folders=[
            GeneratedFolderStat(
                node_id=item.node_id, path=item.path, confidence=item.confidence, reason=item.reason, file_count=item.file_count
            )
            for item in list(generated_folders)[:MAX_LISTED_GENERATED_FOLDERS]
        ],
        generated_folder_count=len(generated_folders),
    )
