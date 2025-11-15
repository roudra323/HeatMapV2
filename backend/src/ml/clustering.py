"""Wallet Clustering Analysis"""
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


class WalletClusterer:
    """Cluster wallets based on behavior patterns"""
    
    def __init__(self, n_clusters: int = 5):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.model = KMeans(n_clusters=n_clusters, random_state=42)
    
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for clustering"""
        features = df[[
            'transaction_count',
            'total_volume',
            'avg_transaction_value',
            'unique_tokens',
        ]].copy()
        
        # Handle missing values
        features = features.fillna(0)
        
        return features
    
    def fit_predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cluster wallets and return results"""
        print(f"Clustering {len(df)} wallets into {self.n_clusters} groups...")
        
        # Prepare features
        features = self.prepare_features(df)
        
        # Scale and cluster
        scaled_features = self.scaler.fit_transform(features)
        clusters = self.model.fit_predict(scaled_features)
        
        # Add cluster labels
        result_df = df.copy()
        result_df['cluster'] = clusters
        
        # Calculate cluster profiles
        profiles = result_df.groupby('cluster').agg({
            'transaction_count': 'mean',
            'total_volume': 'mean',
            'avg_transaction_value': 'mean',
        }).round(2)
        
        print(f"✅ Clustering complete. Profiles:")
        print(profiles)
        
        return result_df