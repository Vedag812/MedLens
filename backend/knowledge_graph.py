"""
MedLens Knowledge Graph Analytics
Builds and analyzes a drug interaction network graph using NetworkX.
Provides graph-based insights like centrality, community detection, and risk paths.
"""

import networkx as nx
from collections import defaultdict
from backend.drug_database import get_all_interactions, get_drug_info, get_all_drug_keys


def build_interaction_graph() -> nx.Graph:
    """
    Build a weighted, undirected graph where:
    - Nodes = drugs
    - Edges = known interactions
    - Edge weight = severity score (CRITICAL=4, SERIOUS=3, MODERATE=2, MINOR=1)
    """
    G = nx.Graph()

    severity_weights = {
        "CRITICAL": 4,
        "SERIOUS": 3,
        "MODERATE": 2,
        "MINOR": 1,
    }

    # Add all drugs as nodes with their metadata
    for key in get_all_drug_keys():
        info = get_drug_info(key)
        if info:
            G.add_node(key, label=info["generic_name"], category=info["category"])

    # Add interaction edges
    for interaction in get_all_interactions():
        a = interaction["drug_a"]
        b = interaction["drug_b"]
        severity = interaction["severity"]
        weight = severity_weights.get(severity, 1)

        G.add_edge(
            a, b,
            weight=weight,
            severity=severity,
            description=interaction["description"],
        )

    return G


def get_graph_statistics(G: nx.Graph) -> dict:
    """
    Compute graph-level statistics for the drug interaction network.
    These are real DS metrics that show analytical depth.
    """
    if G.number_of_nodes() == 0:
        return {}

    # Degree centrality: which drugs interact with the most other drugs
    degree_centrality = nx.degree_centrality(G)

    # Betweenness centrality: which drugs are "bridges" in the interaction network
    betweenness = nx.betweenness_centrality(G, weight="weight")

    # Closeness centrality: how "close" a drug is to all other interacting drugs
    closeness = nx.closeness_centrality(G)

    # Eigenvector centrality: importance based on connections to other important nodes
    try:
        eigenvector = nx.eigenvector_centrality(G, max_iter=500, weight="weight")
    except nx.PowerIterationFailedConvergence:
        eigenvector = {n: 0 for n in G.nodes()}

    # Find the most "dangerous" drugs (highest interaction degree)
    danger_ranking = sorted(
        degree_centrality.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    # Community detection using greedy modularity
    try:
        communities = list(nx.community.greedy_modularity_communities(G))
        community_map = {}
        for i, community in enumerate(communities):
            for node in community:
                community_map[node] = i
    except Exception:
        community_map = {n: 0 for n in G.nodes()}

    # Connected components
    components = list(nx.connected_components(G))

    # Edge statistics by severity
    severity_counts = defaultdict(int)
    for _, _, data in G.edges(data=True):
        severity_counts[data.get("severity", "UNKNOWN")] += 1

    return {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "density": round(nx.density(G), 4),
        "connected_components": len(components),
        "avg_degree": round(sum(dict(G.degree()).values()) / G.number_of_nodes(), 2),
        "severity_distribution": dict(severity_counts),
        "danger_ranking": [
            {
                "drug_key": key,
                "drug_name": get_drug_info(key)["generic_name"] if get_drug_info(key) else key,
                "degree_centrality": round(val, 4),
                "betweenness": round(betweenness.get(key, 0), 4),
                "eigenvector": round(eigenvector.get(key, 0), 4),
                "interaction_count": G.degree(key),
                "community": community_map.get(key, 0),
            }
            for key, val in danger_ranking[:15]
        ],
    }


def get_vault_subgraph_analysis(vault_keys: list[str]) -> dict:
    """
    Analyze just the subgraph formed by the user's vault medications.
    Shows personalized insights about their specific drug combination.
    """
    G = build_interaction_graph()

    # Get the subgraph of vault drugs
    valid_keys = [k for k in vault_keys if k in G.nodes()]
    if len(valid_keys) < 2:
        return {
            "has_data": False,
            "message": "Need at least 2 medications in your vault for graph analysis.",
        }

    subgraph = G.subgraph(valid_keys).copy()

    # Find shortest risk paths between all pairs
    risk_paths = []
    for i, a in enumerate(valid_keys):
        for b in valid_keys[i + 1:]:
            if subgraph.has_edge(a, b):
                edge_data = subgraph[a][b]
                risk_paths.append({
                    "from": get_drug_info(a)["generic_name"] if get_drug_info(a) else a,
                    "to": get_drug_info(b)["generic_name"] if get_drug_info(b) else b,
                    "severity": edge_data.get("severity", "UNKNOWN"),
                    "weight": edge_data.get("weight", 1),
                    "description": edge_data.get("description", ""),
                })

    risk_paths.sort(key=lambda x: x["weight"], reverse=True)

    # Calculate vault risk density
    max_edges = len(valid_keys) * (len(valid_keys) - 1) / 2
    actual_edges = subgraph.number_of_edges()
    risk_density = actual_edges / max_edges if max_edges > 0 else 0

    # Find the highest-risk drug in the vault (most interactions with other vault drugs)
    vault_degrees = dict(subgraph.degree())
    highest_risk_drug = max(vault_degrees, key=vault_degrees.get) if vault_degrees else None

    # Build node data for visualization
    nodes = []
    for key in valid_keys:
        info = get_drug_info(key)
        nodes.append({
            "id": key,
            "label": info["generic_name"] if info else key,
            "category": info["category"] if info else "",
            "interactions_in_vault": subgraph.degree(key),
            "risk_level": "high" if subgraph.degree(key) >= 3 else "medium" if subgraph.degree(key) >= 1 else "low",
        })

    # Build edge data for visualization
    edges = []
    for a, b, data in subgraph.edges(data=True):
        edges.append({
            "source": a,
            "target": b,
            "severity": data.get("severity", "UNKNOWN"),
            "weight": data.get("weight", 1),
        })

    return {
        "has_data": True,
        "drug_count": len(valid_keys),
        "interaction_count": actual_edges,
        "risk_density": round(risk_density, 3),
        "risk_density_pct": round(risk_density * 100, 1),
        "highest_risk_drug": {
            "key": highest_risk_drug,
            "name": get_drug_info(highest_risk_drug)["generic_name"] if highest_risk_drug and get_drug_info(highest_risk_drug) else None,
            "interaction_count": vault_degrees.get(highest_risk_drug, 0) if highest_risk_drug else 0,
        },
        "risk_paths": risk_paths,
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
    }


def get_full_graph_data() -> dict:
    """
    Return the full interaction network for visualization.
    Used by the frontend to render the knowledge graph.
    """
    G = build_interaction_graph()

    severity_colors = {
        "CRITICAL": "#ef4444",
        "SERIOUS": "#f97316",
        "MODERATE": "#eab308",
        "MINOR": "#22c55e",
    }

    nodes = []
    for key in G.nodes():
        info = get_drug_info(key)
        nodes.append({
            "id": key,
            "label": info["generic_name"] if info else key,
            "category": info["category"] if info else "",
            "degree": G.degree(key),
            "size": 8 + G.degree(key) * 3,
        })

    edges = []
    for a, b, data in G.edges(data=True):
        sev = data.get("severity", "MINOR")
        edges.append({
            "source": a,
            "target": b,
            "severity": sev,
            "color": severity_colors.get(sev, "#64748b"),
            "width": data.get("weight", 1),
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": get_graph_statistics(G),
    }
