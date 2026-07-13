# -*- coding: utf-8 -*-
"""Atom-selection expression parsing shared by calculation workflows."""

import re


class SelectionError(ValueError):
    """Raised when an atom-selection expression cannot be resolved safely."""


class SelectionResolver:
    """Resolve atom IDs, inclusive ranges, and element symbols."""

    @staticmethod
    def resolve(expression, elements) -> tuple[int, ...]:
        total_atoms = len(elements)
        expression = expression or ""

        if not expression.strip():
            if not total_atoms:
                raise SelectionError("表达式未匹配任何原子：当前结构不包含原子")
            return tuple(range(1, total_atoms + 1))

        selected = set()
        known_elements = set(elements)
        tokens = [token for token in re.split(r"[,\s]+", expression.strip()) if token]

        for token in tokens:
            if re.fullmatch(r"\d+", token):
                atom_id = int(token)
                if atom_id < 1 or atom_id > total_atoms:
                    raise SelectionError(f"原子编号超出有效范围 1-{total_atoms}：{token}")
                selected.add(atom_id)
                continue

            range_match = re.fullmatch(r"(\d+)-(\d+)", token)
            if range_match:
                start, end = map(int, range_match.groups())
                if start > end:
                    raise SelectionError(f"原子范围不能倒序：{token}")
                if start < 1 or end > total_atoms:
                    raise SelectionError(f"原子编号超出有效范围 1-{total_atoms}：{token}")
                selected.update(range(start, end + 1))
                continue

            if token not in known_elements:
                raise SelectionError(f"未知元素：{token}")
            selected.update(
                atom_id
                for atom_id, element in enumerate(elements, start=1)
                if element == token
            )

        if not selected:
            raise SelectionError(f"表达式未匹配任何原子：{expression}")
        return tuple(sorted(selected))
