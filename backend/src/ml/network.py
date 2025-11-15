"""Network Analysis for Wallet Relationships"""
import pandas as pd
import networkx as nx
from typing import Dict, List


class NetworkAnalyzer:
    """Analyze wallet interaction networks"""
    
    def __init__(self):
        self.graph = nx.Graph()
    
    def build_graph(self, transfers_df: pd.DataFrame) -> nx.Graph:
        """Build network graph from transfer data"""
        print(f"Building network graph from {len(transfers_df)} transfers...")
        
        self.graph = nx.Graph()
        
        # Add edges from transfers
        for _, row in transfers_df.iterrows():
            from_addr = row.get('from', '')
            to_addr = row.get('to', '')
            value = float(row.get('value', 0))
            
            if from_addr and to_addr:
                if self.graph.has_edge(from_addr, to_addr):
                    # Increase weight if edge exists
                    self.graph[from_addr][to_addr]['weight'] += 1
                    self.graph[from_addr][to_addr]['total_value'] += value
                else:
                    # Add new edge
                    self.graph.add_edge(
                        from_addr, 
                        to_addr,
                        weight=1,
                        total_value=value
                    )
        
        print(f"✅ Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        return self.graph
    
    def calculate_metrics(self) -> pd.DataFrame:
        """Calculate network metrics for each wallet"""
        print("Calculating network metrics...")
        
        metrics = []
        
        for node in self.graph.nodes():
            degree = self.graph.degree(node)
            
            # Calculate centrality metrics
            metrics.append({
                'address': node,
                'degree': degree,
                'clustering_coefficient': nx.clustering(self.graph, node),
            })
        
        df = pd.DataFrame(metrics)
        print(f"✅ Calculated metrics for {len(df)} wallets")
        
        return df
    
    def find_communities(self) -> Dict[str, int]:
        """Detect communities in the network"""
        print("Detecting communities...")
        
        communities = nx.community.greedy_modularity_communities(self.graph)
        
        # Map nodes to community IDs
        community_map = {}
        for i, community in enumerate(communities):
            for node in community:
                community_map[node] = i
        
        print(f"✅ Found {len(communities)} communities")
        return community_map
    
    def export_for_visualization(self) -> Dict:
        """Export graph data for frontend visualization"""
        nodes = [{'id': node} for node in self.graph.nodes()]
        edges = [
            {
                'source': u,
                'target': v,
                'weight': data.get('weight', 1)
            }
            for u, v, data in self.graph.edges(data=True)
        ]
        
        return {
            'nodes': nodes,
            'edges': edges,
            'stats': {
                'node_count': self.graph.number_of_nodes(),
                'edge_count': self.graph.number_of_edges(),
            }
        }