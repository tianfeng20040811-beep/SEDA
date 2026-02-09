"""
Model Registry - Version management and persistence for ML models
"""
import os
import json
import pickle
from datetime import datetime, timezone
from typing import Dict, Optional, List
from pathlib import Path


class ModelRegistry:
    """
    Manages model versioning and persistence to local filesystem
    (Can be extended to MinIO/S3 later)
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize model registry
        
        Args:
            base_dir: Base directory for model storage (default: ./model_store)
        """
        if base_dir is None:
            base_dir = os.getenv("MODEL_STORE_PATH", "./model_store")
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Metadata file
        self.metadata_file = self.base_dir / "models_metadata.json"
        self._load_metadata()
    
    def _load_metadata(self):
        """Load model metadata from disk"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {}
    
    def _save_metadata(self):
        """Save model metadata to disk"""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def generate_version(self, site_id: str, model_type: str = "pv_forecast") -> str:
        """
        Generate new model version string
        
        Args:
            site_id: Site UUID
            model_type: Model type identifier
        
        Returns:
            Version string (e.g., "v20260209_001")
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        
        # Find existing versions for today
        prefix = f"{site_id}_{model_type}_{today}"
        existing = [k for k in self.metadata.keys() if k.startswith(prefix)]
        
        version_num = len(existing) + 1
        version = f"v{today}_{version_num:03d}"
        
        return version
    
    def save_model(
        self,
        site_id: str,
        model_type: str,
        quantile: float,
        model_obj: object,
        metadata: Optional[Dict] = None,
        version: Optional[str] = None
    ) -> str:
        """
        Save a trained model to disk
        
        Args:
            site_id: Site UUID
            model_type: Model type (e.g., "pv_forecast")
            quantile: Quantile level (e.g., 0.1, 0.5, 0.9)
            model_obj: Trained model object (LightGBM Booster)
            metadata: Additional metadata dict
            version: Model version (auto-generated if None)
        
        Returns:
            Model version string
        """
        if version is None:
            version = self.generate_version(site_id, model_type)
        
        # Create model directory
        model_dir = self.base_dir / site_id / model_type / version
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model file
        quantile_str = f"q{int(quantile * 100):02d}"
        model_path = model_dir / f"model_{quantile_str}.pkl"
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_obj, f)
        
        # Update metadata
        model_key = f"{site_id}_{model_type}_{version}_{quantile_str}"
        self.metadata[model_key] = {
            "site_id": site_id,
            "model_type": model_type,
            "version": version,
            "quantile": quantile,
            "model_path": str(model_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {}
        }
        
        self._save_metadata()
        
        return version
    
    def load_model(
        self,
        site_id: str,
        model_type: str,
        quantile: float,
        version: Optional[str] = None
    ) -> Optional[object]:
        """
        Load a trained model from disk
        
        Args:
            site_id: Site UUID
            model_type: Model type
            quantile: Quantile level
            version: Model version (uses latest if None)
        
        Returns:
            Loaded model object or None if not found
        """
        if version is None:
            version = self.get_latest_version(site_id, model_type)
            if version is None:
                return None
        
        quantile_str = f"q{int(quantile * 100):02d}"
        model_key = f"{site_id}_{model_type}_{version}_{quantile_str}"
        
        if model_key not in self.metadata:
            return None
        
        model_path = Path(self.metadata[model_key]["model_path"])
        
        if not model_path.exists():
            return None
        
        with open(model_path, 'rb') as f:
            model_obj = pickle.load(f)
        
        return model_obj
    
    def get_latest_version(
        self,
        site_id: str,
        model_type: str
    ) -> Optional[str]:
        """
        Get the latest model version for a site and model type
        
        Args:
            site_id: Site UUID
            model_type: Model type
        
        Returns:
            Latest version string or None
        """
        prefix = f"{site_id}_{model_type}_"
        matching_keys = [k for k in self.metadata.keys() if k.startswith(prefix)]
        
        if not matching_keys:
            return None
        
        # Sort by created_at timestamp
        versions = {}
        for key in matching_keys:
            version = self.metadata[key]["version"]
            created_at = self.metadata[key]["created_at"]
            if version not in versions or created_at > versions[version]:
                versions[version] = created_at
        
        # Get latest version
        latest_version = max(versions.keys(), key=lambda v: versions[v])
        
        return latest_version
    
    def get_model_info(
        self,
        site_id: str,
        model_type: str,
        version: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get metadata for a model version
        
        Args:
            site_id: Site UUID
            model_type: Model type
            version: Model version (uses latest if None)
        
        Returns:
            Model metadata dict or None
        """
        if version is None:
            version = self.get_latest_version(site_id, model_type)
            if version is None:
                return None
        
        # Find any quantile for this version to get info
        prefix = f"{site_id}_{model_type}_{version}_"
        matching_keys = [k for k in self.metadata.keys() if k.startswith(prefix)]
        
        if not matching_keys:
            return None
        
        # Return metadata from first matching model
        return self.metadata[matching_keys[0]]
    
    def list_versions(
        self,
        site_id: str,
        model_type: str
    ) -> List[Dict]:
        """
        List all model versions for a site and model type
        
        Args:
            site_id: Site UUID
            model_type: Model type
        
        Returns:
            List of dicts with version info
        """
        prefix = f"{site_id}_{model_type}_"
        matching_keys = [k for k in self.metadata.keys() if k.startswith(prefix)]
        
        # Group by version
        versions = {}
        for key in matching_keys:
            meta = self.metadata[key]
            version = meta["version"]
            if version not in versions:
                versions[version] = {
                    "version": version,
                    "created_at": meta["created_at"],
                    "quantiles": [],
                    "metadata": meta.get("metadata", {})
                }
            versions[version]["quantiles"].append(meta["quantile"])
        
        # Sort by created_at descending
        result = sorted(versions.values(), key=lambda x: x["created_at"], reverse=True)
        
        return result


if __name__ == "__main__":
    # Test model registry
    import tempfile
    import shutil
    
    # Create temporary directory for testing
    temp_dir = tempfile.mkdtemp()
    
    try:
        print("Model Registry Test")
        print("=" * 60)
        
        registry = ModelRegistry(base_dir=temp_dir)
        
        # Test 1: Save models
        print("\n1. Save models:")
        site_id = "11111111-1111-1111-1111-111111111111"
        model_type = "pv_forecast"
        
        # Create dummy model objects
        for quantile in [0.1, 0.5, 0.9]:
            dummy_model = {"quantile": quantile, "params": {"learning_rate": 0.1}}
            
            version = registry.save_model(
                site_id=site_id,
                model_type=model_type,
                quantile=quantile,
                model_obj=dummy_model,
                metadata={"training_samples": 1000, "mae": 5.2}
            )
            
            print(f"Saved q{int(quantile*100):02d} model -> version: {version}")
        
        # Test 2: Load models
        print("\n2. Load models:")
        for quantile in [0.1, 0.5, 0.9]:
            loaded_model = registry.load_model(site_id, model_type, quantile)
            print(f"Loaded q{int(quantile*100):02d}: {loaded_model}")
        
        # Test 3: Get latest version
        print("\n3. Get latest version:")
        latest = registry.get_latest_version(site_id, model_type)
        print(f"Latest version: {latest}")
        
        # Test 4: Get model info
        print("\n4. Get model info:")
        info = registry.get_model_info(site_id, model_type)
        print(f"Model info: {json.dumps(info, indent=2)}")
        
        # Test 5: List versions
        print("\n5. List versions:")
        versions = registry.list_versions(site_id, model_type)
        for v in versions:
            print(f"  {v['version']:20s} | Quantiles: {v['quantiles']} | Created: {v['created_at']}")
        
    finally:
        # Clean up
        shutil.rmtree(temp_dir)
        print(f"\nCleaned up test directory: {temp_dir}")
