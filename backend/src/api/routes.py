"""API Routes"""
from fastapi import APIRouter, HTTPException, Query
from typing import List
import pandas as pd
from pathlib import Path
import json

from .models import (
    WalletResponse,
    WalletListResponse,
    ClusterResponse,
    AnomalyResponse,
    StatsResponse,
    NetworkResponse
)

router = APIRouter()
DATA_DIR = Path("data")


@router.get("/", tags=["root"])
def read_root():
    """API root endpoint"""
    return {
        "message": "HeatMap API",
        "version": "2.0.0",
        "endpoints": [
            "/api/wallets",
            "/api/clusters",
            "/api/anomalies",
            "/api/network",
            "/api/stats",
            "/api/visualization",
            "/api/communities",
            "/api/embeddings"
        ]
    }


@router.get("/api/wallets", response_model=WalletListResponse, tags=["wallets"])
def get_wallets(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0)
):
    """Get paginated list of wallets"""
    try:
        df = pd.read_csv(DATA_DIR / "processed/wallets.csv")
        total = len(df)
        
        # Paginate
        wallets_df = df.iloc[skip:skip+limit]
        wallets = wallets_df.to_dict('records')
        
        return {
            "total": total,
            "wallets": wallets,
            "limit": limit,
            "skip": skip
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wallets data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/wallets/{address}", response_model=WalletResponse, tags=["wallets"])
def get_wallet_details(address: str):
    """Get specific wallet details"""
    try:
        df = pd.read_csv(DATA_DIR / "processed/wallets.csv")
        wallet = df[df['address'].str.lower() == address.lower()]
        
        if wallet.empty:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        return wallet.to_dict('records')[0]
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wallets data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/clusters", response_model=List[ClusterResponse], tags=["analysis"])
def get_clusters():
    """Get clustering analysis results"""
    try:
        df = pd.read_csv(DATA_DIR / "results/clusters.csv")
        
        # Aggregate by cluster
        clusters = df.groupby('cluster').agg({
            'address': 'count',
            'transaction_count': 'mean',
            'total_volume': 'mean',
        }).reset_index()
        
        clusters.columns = ['cluster_id', 'size', 'avg_transaction_count', 'avg_total_volume']
        
        return clusters.to_dict('records')
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Cluster data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/anomalies", response_model=List[AnomalyResponse], tags=["analysis"])
def get_anomalies():
    """Get anomaly detection results"""
    try:
        df = pd.read_csv(DATA_DIR / "results/anomalies.csv")
        anomalies = df[df['is_anomaly'] == True]
        
        return anomalies.to_dict('records')
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Anomaly data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/network", response_model=NetworkResponse, tags=["analysis"])
def get_network():
    """Get network graph data"""
    try:
        with open(DATA_DIR / "results/network.json") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Network data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats", response_model=StatsResponse, tags=["statistics"])
def get_stats():
    """Get overall statistics"""
    try:
        wallets_df = pd.read_csv(DATA_DIR / "processed/wallets.csv")
        
        stats = {
            "total_wallets": len(wallets_df),
            "total_clusters": 0,
            "total_anomalies": 0,
            "total_transactions": int(wallets_df['transaction_count'].sum()) if 'transaction_count' in wallets_df else 0
        }
        
        # Try to get cluster count
        try:
            clusters_df = pd.read_csv(DATA_DIR / "results/clusters.csv")
            stats["total_clusters"] = clusters_df['cluster'].nunique()
        except:
            pass
        
        # Try to get anomaly count
        try:
            anomalies_df = pd.read_csv(DATA_DIR / "results/anomalies.csv")
            stats["total_anomalies"] = len(anomalies_df[anomalies_df['is_anomaly'] == True])
        except:
            pass
        
        return stats
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/visualization", tags=["visualization"])
def get_visualization_data():
    """Get complete visualization data (embeddings, communities, network)"""
    try:
        with open(DATA_DIR / "results/visualization_data.json") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Visualization data not found. Run 'python visualize.py' first."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/communities", tags=["visualization"])
def get_communities():
    """Get behavior-based community statistics"""
    try:
        with open(DATA_DIR / "results/visualization_data.json") as f:
            data = json.load(f)
        return {
            "communities": data.get("community_stats", []),
            "total": len(data.get("community_stats", []))
        }
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Visualization data not found. Run 'python visualize.py' first."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/embeddings", tags=["visualization"])
def get_embeddings(
    method: str = Query("tsne", regex="^(pca|tsne)$"),
    community: str = Query(None)
):
    """Get PCA or t-SNE embeddings, optionally filtered by community"""
    try:
        with open(DATA_DIR / "results/visualization_data.json") as f:
            data = json.load(f)

        wallets = data.get("wallets", [])

        # Filter by community if specified
        if community:
            wallets = [w for w in wallets if w.get("community") == community]

        # Extract relevant coordinates
        if method == "pca":
            embeddings = [
                {
                    "address": w["address"],
                    "x": w["pca_x"],
                    "y": w["pca_y"],
                    "community": w["community"],
                    "total_transactions": w["total_transactions"]
                }
                for w in wallets
            ]
        else:  # tsne
            embeddings = [
                {
                    "address": w["address"],
                    "x": w["tsne_x"],
                    "y": w["tsne_y"],
                    "community": w["community"],
                    "total_transactions": w["total_transactions"]
                }
                for w in wallets
            ]

        return {
            "method": method,
            "community_filter": community,
            "total": len(embeddings),
            "embeddings": embeddings
        }
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Visualization data not found. Run 'python visualize.py' first."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))