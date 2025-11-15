"""Anomaly Detection for Wallets"""
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class AnomalyDetector:
    """Detect anomalous wallet behavior"""
    
    def __init__(self, contamination: float = 0.1):
        self.contamination = contamination
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42
        )
    
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for anomaly detection"""
        features = df[[
            'transaction_count',
            'total_volume',
            'avg_transaction_value',
            'unique_tokens',
            'unique_counterparties',
        ]].copy()
        
        features = features.fillna(0)
        return features
    
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies and return results"""
        print(f"Detecting anomalies in {len(df)} wallets...")
        
        # Prepare features
        features = self.prepare_features(df)
        
        # Scale and detect
        scaled_features = self.scaler.fit_transform(features)
        predictions = self.model.fit_predict(scaled_features)
        scores = self.model.score_samples(scaled_features)
        
        # Add results
        result_df = df.copy()
        result_df['is_anomaly'] = predictions == -1
        result_df['anomaly_score'] = scores
        
        # Get anomalies
        anomalies = result_df[result_df['is_anomaly']]
        
        print(f"✅ Found {len(anomalies)} anomalous wallets ({len(anomalies)/len(df)*100:.1f}%)")
        
        return result_df