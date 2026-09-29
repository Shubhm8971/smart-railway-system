"""
route_finder.py
---------------
Dijkstra's shortest path over the station graph using a binary min-heap (heapq).

Complexity: O((V + E) log V)
Graph format: {station: [(neighbour, distance_km), ...]}  (undirected tracks)
"""
from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple

Graph = Dict[str, List[Tuple[str, float]]]


def build_graph(edges: List[Tuple[str, str, float]]) -> Graph:
    """Build an undirected adjacency list from (a, b, km) edges."""
    graph: Graph = {}
    for a, b, km in edges:
        graph.setdefault(a, []).append((b, km))
        graph.setdefault(b, []).append((a, km))
    return graph


def shortest_path(graph: Graph, source: str, target: str
                  ) -> Optional[Tuple[float, List[str]]]:
    """Return (total_km, [stations...]) or None if no route exists."""
    if source not in graph or target not in graph:
        return None

    dist: Dict[str, float] = {source: 0.0}
    prev: Dict[str, str] = {}
    heap: List[Tuple[float, str]] = [(0.0, source)]       # (distance, node)

    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, float("inf")):
            continue                                        # stale entry, skip
        if node == target:
            break                                           # early exit
        for neighbour, km in graph[node]:
            nd = d + km
            if nd < dist.get(neighbour, float("inf")):
                dist[neighbour] = nd
                prev[neighbour] = node
                heapq.heappush(heap, (nd, neighbour))

    if target not in dist:
        return None

    path, cur = [target], target
    while cur != source:
        cur = prev[cur]
        path.append(cur)
    return round(dist[target], 1), path[::-1]


def base_fare_for_distance(km: float, rate_per_km: float = 1.2, minimum: float = 60) -> float:
    """Simple distance-based base fare that feeds the profit optimizer."""
    return round(max(minimum, km * rate_per_km), 2)


# Demo network (approximate distances, for demonstration only)
DEMO_EDGES = [
    ("Agra Cantt", "Mathura", 58), ("Mathura", "New Delhi", 141),
    ("Agra Cantt", "Gwalior", 118), ("Gwalior", "Jhansi", 101),
    ("Jhansi", "Bhopal", 291), ("Agra Cantt", "Etawah", 122),
    ("Etawah", "Kanpur", 175), ("Kanpur", "Lucknow", 76),
    ("New Delhi", "Kanpur", 440), ("Jhansi", "Kanpur", 210),
]
DEMO_GRAPH = build_graph(DEMO_EDGES)

if __name__ == "__main__":
    print(shortest_path(DEMO_GRAPH, "Agra Cantt", "Lucknow"))
    print(shortest_path(DEMO_GRAPH, "Agra Cantt", "Bhopal"))
