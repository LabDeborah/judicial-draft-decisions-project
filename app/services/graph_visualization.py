from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.utils.fs import ensure_dir, write_text

try:
    from rdflib import Graph
    from rdflib import Literal
    from rdflib import URIRef
    from rdflib.namespace import RDF
    from rdflib.namespace import RDFS
except ImportError:  # pragma: no cover - optional dependency at runtime
    Graph = None
    Literal = None
    URIRef = None
    RDF = None
    RDFS = None


@dataclass(slots=True)
class GraphVisualizationArtifacts:
    dot_path: str
    svg_path: str | None


@dataclass(slots=True)
class _NodeSpec:
    node_id: str
    label: str
    cluster: str
    fillcolor: str
    color: str
    tooltip: str = ""
    shape: str = "box"
    style: str = "rounded,filled"
    fontsize: str = "12"


def render_rdf_graph_visualization(ttl_path: str, *, output_dir: str) -> GraphVisualizationArtifacts | None:
    return _render_rdf_graph_visualization(ttl_path, output_dir=output_dir, variant="executive")


def _render_rdf_graph_visualization(
    ttl_path: str,
    *,
    output_dir: str,
    variant: str,
) -> GraphVisualizationArtifacts | None:
    if Graph is None:
        return None
    ttl_file = Path(ttl_path)
    graph = Graph()
    graph.parse(ttl_file, format="turtle")
    ensure_dir(output_dir)
    dot_path = str(Path(output_dir) / f"{ttl_file.stem}.dot")
    write_text(dot_path, _graph_to_dot(graph, variant=variant))
    svg_path = _render_dot_to_svg(dot_path)
    return GraphVisualizationArtifacts(dot_path=dot_path, svg_path=svg_path)


def _graph_to_dot(graph: Graph, *, variant: str) -> str:
    node_specs = _collect_node_specs(graph, variant=variant)
    suppressed_literals = _collect_suppressed_literals(graph)
    cluster_order = _cluster_order(variant)
    lines = [
        "digraph rdf_graph {",
        '  rankdir=LR;',
        _graph_style_line(variant),
        '  node [shape=box, style="rounded,filled", fillcolor="#f8fafc", color="#334155", fontname="Helvetica"];',
        '  edge [color="#475569", fontname="Helvetica", fontsize="10"];',
    ]
    edges: list[str] = []
    for cluster_name in cluster_order:
        cluster_nodes = [spec for spec in node_specs.values() if spec.cluster == cluster_name]
        if not cluster_nodes:
            continue
        lines.extend(_cluster_block(cluster_name, cluster_nodes))
    for subject, predicate, obj in sorted(graph, key=lambda triple: tuple(str(item) for item in triple)):
        if _should_suppress_literal_node(predicate, obj):
            continue
        if variant == "executive" and not _include_executive_edge(subject, predicate, obj, node_specs):
            continue
        subject_id = _node_id(subject)
        object_id = _node_id(obj)
        if subject_id not in node_specs or object_id not in node_specs:
            continue
        edges.append(
            _edge_line(subject_id, object_id, _predicate_label(predicate), variant=variant)
        )
    lines.extend(edges)
    lines.append("}")
    return "\n".join(lines) + "\n"


def _cluster_order(variant: str) -> list[str]:
    base = [
        "workflow",
        "decision",
        "petition",
        "theme",
        "analysis",
        "document",
        "literal",
        "meta",
        "other",
    ]
    return [name for name in base if name not in {"literal", "meta", "other"}]


def _graph_style_line(variant: str) -> str:
    return '  graph [bgcolor="white", pad="0.35", nodesep="0.75", ranksep="1.35", splines=ortho, overlap=false, concentrate=true];'


def _collect_node_specs(graph: Graph, *, variant: str) -> dict[str, _NodeSpec]:
    type_index = _build_type_index(graph)
    suppressed_literals = _collect_suppressed_literals(graph)
    specs: dict[str, _NodeSpec] = {}
    for subject, predicate, obj in graph:
        for term in (subject, obj):
            if _should_skip_term(predicate, term):
                continue
            node_id = _node_id(term)
            if node_id in specs:
                continue
            spec = _build_node_spec(term, graph, type_index, suppressed_literals.get(str(term), []))
            if spec.cluster in {"literal", "meta", "other"}:
                continue
            specs[node_id] = spec
    return specs


def _build_type_index(graph: Graph) -> dict[str, set[str]]:
    type_index: dict[str, set[str]] = {}
    if RDF is None:
        return type_index
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        type_index.setdefault(str(subject), set()).add(_normalized_term(obj, graph))
    return type_index


def _build_node_spec(
    term,
    graph: Graph,
    type_index: dict[str, set[str]],
    tooltip_lines: list[str],
) -> _NodeSpec:
    node_id = _node_id(term)
    label = _truncate(_term_label(term, graph), 90)
    tooltip = _tooltip_text(label, tooltip_lines)
    if Literal is not None and isinstance(term, Literal):
        return _NodeSpec(
            node_id=node_id,
            label=label,
            cluster="literal",
            fillcolor="#fff7ed",
            color="#c2410c",
            tooltip=tooltip,
            shape="note",
            fontsize="11",
        )
    normalized = _normalized_term(term, graph)
    term_types = type_index.get(str(term), set())
    if normalized.startswith("jdd:pipeline") or "prov:SoftwareAgent" in term_types:
        return _NodeSpec(node_id, label, "workflow", "#dbeafe", "#1d4ed8", tooltip=tooltip)
    if "prov:Activity" in term_types:
        return _NodeSpec(node_id, label, "workflow", "#dbeafe", "#1d4ed8", tooltip=tooltip, shape="component")
    if "ors:Theme" in term_types:
        return _NodeSpec(node_id, label, "theme", "#dcfce7", "#15803d", tooltip=tooltip)
    if "ors:Thesis" in term_types:
        return _NodeSpec(node_id, label, "theme", "#ecfccb", "#4d7c0f", tooltip=tooltip)
    if "ors:Petition" in term_types:
        return _NodeSpec(node_id, label, "petition", "#fee2e2", "#b91c1c", tooltip=tooltip)
    if "ors:AdmissibilityDecision" in term_types:
        return _NodeSpec(node_id, label, "document", "#fce7f3", "#be185d", tooltip=tooltip)
    if "ors:AppellateDecisionOnSFCA" in term_types:
        return _NodeSpec(node_id, label, "decision", "#e0e7ff", "#4338ca", tooltip=tooltip)
    if normalized.startswith("jdd:generated-decision") or normalized.startswith("jdd:analysis"):
        return _NodeSpec(node_id, label, "analysis", "#ede9fe", "#6d28d9", tooltip=tooltip)
    if normalized.startswith("tnu:") or normalized.startswith("thesis:"):
        return _NodeSpec(node_id, label, "theme", "#dcfce7", "#15803d", tooltip=tooltip)
    if normalized.startswith("tres:"):
        return _NodeSpec(node_id, label, "decision", "#e0e7ff", "#4338ca", tooltip=tooltip)
    if normalized.startswith("rs:"):
        return _NodeSpec(node_id, label, "petition", "#fee2e2", "#b91c1c", tooltip=tooltip)
    if normalized.startswith("prov:") or normalized.startswith("ors:") or normalized.startswith("rdfs:") or normalized.startswith("dcterms:"):
        return _NodeSpec(node_id, label, "meta", "#e2e8f0", "#475569", tooltip=tooltip, shape="tab")
    return _NodeSpec(node_id, label, "other", "#f8fafc", "#334155", tooltip=tooltip)


def _cluster_block(cluster_name: str, cluster_nodes: list[_NodeSpec]) -> list[str]:
    title, color = _cluster_style(cluster_name)
    lines = [
        f'  subgraph "cluster_{cluster_name}" {{',
        f'    label="{title}";',
        f'    color="{color}";',
        '    style="rounded,dashed";',
        '    penwidth=1.2;',
    ]
    for spec in sorted(cluster_nodes, key=lambda item: item.label.lower()):
        lines.append(
            "    "
            + f'{spec.node_id} [label="{_escape_dot(spec.label)}", shape="{spec.shape}", style="{spec.style}", '
            + f'fillcolor="{spec.fillcolor}", color="{spec.color}", fontsize="{spec.fontsize}", '
            + f'tooltip="{_escape_dot(spec.tooltip or spec.label)}"];'
        )
    lines.append("  }")
    return lines


def _cluster_style(cluster_name: str) -> tuple[str, str]:
    styles = {
        "workflow": ("Workflow / Agents", "#93c5fd"),
        "decision": ("Decision", "#a5b4fc"),
        "petition": ("Petition", "#fca5a5"),
        "theme": ("Theme / Thesis", "#86efac"),
        "analysis": ("Analysis / Generated Resources", "#c4b5fd"),
        "document": ("Document Outcome", "#f9a8d4"),
        "literal": ("Literal Values", "#fdba74"),
        "meta": ("Ontology / Metadata", "#cbd5e1"),
        "other": ("Other Resources", "#cbd5e1"),
    }
    return styles.get(cluster_name, ("Other Resources", "#cbd5e1"))


def _edge_line(subject_id: str, object_id: str, predicate_label: str, *, variant: str) -> str:
    color = "#334155"
    style = "solid"
    penwidth = "1.6"
    return (
        f'  {subject_id} -> {object_id} [label="{_escape_dot(predicate_label)}", '
        f'color="{color}", style="{style}", penwidth="{penwidth}"];'
    )


def _term_label(term, graph: Graph) -> str:
    if Literal is not None and isinstance(term, Literal):
        return str(term)
    if RDFS is not None:
        label = graph.value(term, RDFS.label)
        if label:
            return str(label)
    value = graph.namespace_manager.normalizeUri(term)
    return value.replace("<", "").replace(">", "")


def _predicate_label(predicate) -> str:
    value = str(predicate)
    for separator in ("#", "/"):
        if separator in value:
            value = value.rsplit(separator, 1)[-1]
    return value


def _node_id(term) -> str:
    return f'n{abs(hash(str(term)))}'


def _node_line(node_id: str, label: str) -> str:
    return f'  {node_id} [label="{_escape_dot(_truncate(label, 120))}"];'


def _truncate(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _escape_dot(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _normalized_term(term: Any, graph: Graph) -> str:
    if URIRef is not None and isinstance(term, URIRef):
        return graph.namespace_manager.normalizeUri(term).replace("<", "").replace(">", "")
    return str(term)


def _collect_suppressed_literals(graph: Graph) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = {}
    for subject, predicate, obj in graph:
        if not _should_suppress_literal_node(predicate, obj):
            continue
        subject_key = str(subject)
        predicate_label = _predicate_label(predicate)
        value = " ".join(str(obj).split())
        collected.setdefault(subject_key, []).append(f"{predicate_label}: {_truncate(value, 220)}")
    return collected


def _should_skip_term(predicate, term: Any) -> bool:
    return _should_suppress_literal_node(predicate, term)


def _should_suppress_literal_node(predicate, obj: Any) -> bool:
    if Literal is None or not isinstance(obj, Literal):
        return False
    label = _predicate_label(predicate)
    value = " ".join(str(obj).split())
    if label in {"description", "themeThesis", "subject"} and len(value) > 48:
        return True
    if label == "atLocation" and len(value) > 64:
        return True
    return False


def _tooltip_text(label: str, tooltip_lines: list[str]) -> str:
    if not tooltip_lines:
        return label
    content = [label, ""] + tooltip_lines
    return "\n".join(content)


def _include_executive_edge(subject, predicate, obj, node_specs: dict[str, _NodeSpec]) -> bool:
    predicate_label = _predicate_label(predicate)
    if predicate_label not in {
        "used",
        "generated",
        "wasDerivedFrom",
        "wasGeneratedBy",
        "wasAssociatedWith",
        "wasInformedBy",
        "adoptsThesis",
        "hasTheme",
        "isFiledAgainst",
        "ruledIn",
    }:
        return False
    return _node_id(subject) in node_specs and _node_id(obj) in node_specs


def _render_dot_to_svg(dot_path: str) -> str | None:
    dot_bin = _resolve_dot_binary()
    if not dot_bin:
        return None
    svg_path = str(Path(dot_path).with_suffix(".svg"))
    completed = subprocess.run(
        [dot_bin, "-Tsvg", dot_path, "-o", svg_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if completed.returncode != 0 or not Path(svg_path).exists():
        return None
    return svg_path


def _resolve_dot_binary() -> str | None:
    dot_bin = shutil.which("dot")
    if dot_bin:
        return dot_bin
    local_candidates = sorted(Path("tools/graphviz").glob("**/bin/dot.exe"))
    if local_candidates:
        return str(local_candidates[0])
    return None
