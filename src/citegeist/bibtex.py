from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BibEntry:
    entry_type: str
    citation_key: str
    fields: dict[str, str]


def parse_bibtex(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    index = 0
    size = len(text)

    while index < size:
        at = text.find("@", index)
        if at == -1:
            break
        entry_type_start = at + 1
        brace = text.find("{", entry_type_start)
        if brace == -1:
            raise ValueError("Malformed BibTeX: missing opening brace")
        entry_type = text[entry_type_start:brace].strip().lower()
        body, index = _read_balanced_block(text, brace)
        citation_key, fields_blob = _split_key_and_fields(body)
        entries.append(
            BibEntry(
                entry_type=entry_type,
                citation_key=citation_key,
                fields=_parse_fields(fields_blob),
            )
        )

    return entries


def _read_balanced_block(text: str, brace_index: int) -> tuple[str, int]:
    depth = 0
    in_quotes = False
    escaped = False

    for index in range(brace_index, len(text)):
        char = text[index]
        if in_quotes:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quotes = False
            continue

        if char == '"':
            in_quotes = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index + 1:index], index + 1

    raise ValueError("Malformed BibTeX: unbalanced braces")


def _split_key_and_fields(body: str) -> tuple[str, str]:
    depth = 0
    in_quotes = False
    escaped = False

    for index, char in enumerate(body):
        if in_quotes:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quotes = False
            continue

        if char == '"':
            in_quotes = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "," and depth == 0:
            return body[:index].strip(), body[index + 1 :]

    return body.strip(), ""


def _parse_fields(blob: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    size = len(blob)

    while index < size:
        while index < size and blob[index] in " \t\r\n,":
            index += 1
        if index >= size:
            break

        name_start = index
        while index < size and (blob[index].isalnum() or blob[index] in "-_"):
            index += 1
        name = blob[name_start:index].strip().lower()

        while index < size and blob[index].isspace():
            index += 1
        if index >= size or blob[index] != "=":
            raise ValueError(f"Malformed BibTeX field near: {blob[name_start:]!r}")
        index += 1

        while index < size and blob[index].isspace():
            index += 1
        value, index = _parse_value(blob, index)
        fields[name] = " ".join(value.split())

        while index < size and blob[index] in " \t\r\n,":
            index += 1

    return fields


def _parse_value(blob: str, index: int) -> tuple[str, int]:
    if index >= len(blob):
        return "", index

    if blob[index] == "{":
        value, next_index = _read_balanced_block(blob, index)
        return value.strip(), next_index

    if blob[index] == '"':
        index += 1
        chars: list[str] = []
        escaped = False
        while index < len(blob):
            char = blob[index]
            if escaped:
                chars.append(char)
                escaped = False
            elif char == "\\":
                chars.append(char)
                escaped = True
            elif char == '"':
                return "".join(chars).strip(), index + 1
            else:
                chars.append(char)
            index += 1
        raise ValueError("Malformed BibTeX: unterminated quoted string")

    end = index
    while end < len(blob) and blob[end] not in ",\r\n":
        end += 1
    return blob[index:end].strip(), end
