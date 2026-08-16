import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TextPiece:
    text: str
    start_time: float | None = None
    end_time: float | None = None


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip()


class TextChunker:
    def __init__(self, chunk_size: int, overlap: int) -> None:
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, pieces: list[TextPiece]) -> list[TextPiece]:
        chunks: list[TextPiece] = []
        for piece in pieces:
            text = normalize_text(piece.text)
            if not text:
                continue
            start = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                if end < len(text):
                    boundary = text.rfind(" ", start, end)
                    if boundary > start:
                        end = boundary
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append(TextPiece(chunk_text, piece.start_time, piece.end_time))
                if end >= len(text):
                    break
                start = max(end - self.overlap, start + 1)
        return chunks
