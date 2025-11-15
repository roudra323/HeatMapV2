"""Pydantic Models for API Responses"""
from typing import List, Optional
from pydantic import BaseModel


class WalletResponse(BaseModel):
    """Wallet data response"""
    address: str
    balance: Optional[float] = 0
    transaction_count: Optional[int] = 0
    total_volume: Optional[float] = 0
    cluster: Optional[int] = None
    is_anomaly: Optional[bool] = False


class ClusterResponse(BaseModel):
    """Cluster data response"""
    cluster_id: int
    size: int
    avg_transaction_count: float
    avg_total_volume: float


class AnomalyResponse(BaseModel):
    """Anomaly data response"""
    address: str
    anomaly_score: float
    reason: Optional[str] = None


class StatsResponse(BaseModel):
    """Overall statistics response"""
    total_wallets: int
    total_clusters: int
    total_anomalies: int
    total_transactions: Optional[int] = 0


class NetworkResponse(BaseModel):
    """Network graph response"""
    nodes: List[dict]
    edges: List[dict]
    stats: dict


class WalletListResponse(BaseModel):
    """Paginated wallet list response"""
    total: int
    wallets: List[WalletResponse]
    limit: int
    skip: int