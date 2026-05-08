"""Chart generation tools — matplotlib-based PNG charts."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

from config import GENERATED_DIR

CHARTS_DIR = GENERATED_DIR / "figures"


def _save_plot(fig, name: str) -> str:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{name}_{uuid.uuid4().hex[:6]}.png"
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return json.dumps({"path": str(path), "file": path.name}, ensure_ascii=False)


def tool_chart_line(title: str, x_label: str, y_label: str,
                    data_json: str, output_name: str = "line_chart") -> str:
    """Generate a PNG line chart. Args: title, x_label, y_label,
    data_json = [{"label": "Series1", "x": [1,2,3], "y": [10,20,15]}, ...].
    """
    import matplotlib.pyplot as plt

    try:
        series_list = json.loads(data_json)
    except json.JSONDecodeError as e:
        return f"Error: {e}"

    fig, ax = plt.subplots(figsize=(8, 5))
    for s in series_list:
        ax.plot(s.get("x", []), s.get("y", []), marker="o", label=s.get("label", ""))
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if any(s.get("label") for s in series_list):
        ax.legend()
    ax.grid(True, alpha=0.3)
    return _save_plot(fig, output_name)


def tool_chart_bar(title: str, x_label: str, y_label: str,
                   data_json: str, output_name: str = "bar_chart") -> str:
    """Generate a PNG bar chart. Args: title, x_label, y_label,
    data_json = [{"label": "A", "value": 10}, ...].
    """
    import matplotlib.pyplot as plt

    try:
        items = json.loads(data_json)
    except json.JSONDecodeError as e:
        return f"Error: {e}"

    labels = [i.get("label", "") for i in items]
    values = [i.get("value", 0) for i in items]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, values)
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(True, alpha=0.3, axis="y")
    return _save_plot(fig, output_name)


def tool_chart_confusion_matrix(labels_json: str, matrix_json: str,
                                 output_name: str = "confusion_matrix") -> str:
    """Generate a PNG confusion matrix heatmap.
    Args: labels_json (JSON array of class names), matrix_json (JSON 2D array).
    """
    import matplotlib.pyplot as plt

    try:
        labels = json.loads(labels_json)
        matrix = json.loads(matrix_json)
    except json.JSONDecodeError as e:
        return f"Error: {e}"

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    for i in range(len(matrix)):
        for j in range(len(matrix[0]) if matrix else 0):
            ax.text(j, i, matrix[i][j], ha="center", va="center")
    ax.set_title("Confusion Matrix")
    fig.colorbar(im)
    return _save_plot(fig, output_name)


def tool_chart_training_curves(history_json: str, output_name: str = "training_curves") -> str:
    """Generate PNG training curves from a history dict.
    Args: history_json = {"loss": [1.0, 0.5, ...], "val_loss": [1.2, 0.6, ...], ...}.
    """
    import matplotlib.pyplot as plt

    try:
        history = json.loads(history_json)
        if not isinstance(history, dict):
            return "Error: history_json must be a JSON object with numeric list values"
        for k, v in history.items():
            if not isinstance(v, list) or not all(isinstance(x, (int, float)) for x in v):
                return f"Error: key '{k}' must be a list of numbers, got {type(v).__name__}"
    except json.JSONDecodeError as e:
        return f"Error: {e}"

    metrics = [k for k in history if not k.startswith("val_")]
    fig, axes = plt.subplots(1, len(metrics), figsize=(6 * len(metrics), 4))
    if len(metrics) == 1:
        axes = [axes]

    for ax, metric in zip(axes, metrics):
        ax.plot(history[metric], label=f"train {metric}")
        val_key = f"val_{metric}"
        if val_key in history:
            ax.plot(history[val_key], label=f"val {metric}")
        ax.set_title(metric)
        ax.set_xlabel("epoch")
        ax.legend()
        ax.grid(True, alpha=0.3)

    return _save_plot(fig, output_name)


# ── Mermaid / Mindmap ─────────────────────────────────

def tool_mermaid_mindmap(title: str, nodes: str) -> str:
    """Create a Mermaid mindmap block from an indented outline.
    Pass nodes as lines where indentation represents depth.
    The title is escaped to prevent breaking Mermaid syntax."""
    clean_title = (title or "Mindmap").strip()
    # Escape double-quotes that could break Mermaid syntax
    clean_title = clean_title.replace('"', '\\"')
    body = "\n".join("  " + line.rstrip() for line in nodes.splitlines() if line.strip())
    return f"```mermaid\nmindmap\n  root(({clean_title}))\n{body}\n```"


def tool_mermaid_flowchart(title: str, definition: str) -> str:
    """Create a Mermaid flowchart / graph block.
    Pass a title and the Mermaid graph definition (nodes + edges)."""
    clean_title = (title or "Flowchart").strip()
    return f"```mermaid\ngraph TD\n  %% {clean_title}\n{definition.strip()}\n```"
