import numpy as np
from sklearn.cluster import DBSCAN


def cluster_embeddings(
    embeddings: list[list[float]], similarity_threshold: float, min_samples: int
) -> list[int]:
    if not embeddings:
        return []
    if len(embeddings) == 1:
        return [0]
    matrix = np.asarray(embeddings, dtype=np.float32)
    labels = DBSCAN(
        eps=1.0 - similarity_threshold,
        min_samples=min_samples,
        metric="cosine",
        algorithm="brute",
    ).fit_predict(matrix).tolist()
    next_label = max((label for label in labels if label >= 0), default=-1) + 1
    for index, label in enumerate(labels):
        if label == -1:
            labels[index] = next_label
            next_label += 1
    return labels
