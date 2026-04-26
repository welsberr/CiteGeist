"""
Source registry for managing bibliographic source plugins.

This module provides a registry that can discover, load, and manage
multiple bibliographic source plugins.
"""
from __future__ import annotations

import importlib.util
import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from citegeist.sources.base import BibliographicSource


@dataclass(slots=True)
class SourceRegistration:
    """Registration information for a source plugin."""
    name: str
    source_class: Type[BibliographicSource]
    config: Dict[str, Any]
    enabled: bool


class SourceRegistry:
    """Registry for bibliographic source plugins.
    
    This class manages the discovery, registration, and instantiation
    of bibliographic source plugins.
    """
    
    def __init__(self) -> None:
        """Initialize the source registry."""
        self._registrations: Dict[str, SourceRegistration] = {}
        self._instances: Dict[str, BibliographicSource] = {}
    
    def register(
        self,
        source_class: Type[BibliographicSource],
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a source class.
        
        Args:
            source_class: The source class to register (must inherit from BibliographicSource)
            name: Optional name for the source (uses class name if not provided)
            config: Optional configuration dictionary
        """
        if not inspect.isclass(source_class) or not issubclass(source_class, BibliographicSource):
            raise ValueError(f"{source_class} must be a subclass of BibliographicSource")
        
        source_name = name or source_class.__name__
        self._registrations[source_name] = SourceRegistration(
            name=source_name,
            source_class=source_class,
            config=config or {},
            enabled=config.get('enabled', True) if config else True
        )
    
    def get(self, name: str) -> Optional[BibliographicSource]:
        """Get a source instance by name.
        
        Args:
            name: Name of the source
            
        Returns:
            Source instance if registered and enabled, None otherwise
        """
        if name not in self._registrations:
            return None
        
        registration = self._registrations[name]
        
        # Return cached instance if available
        if name in self._instances:
            return self._instances[name]
        
        # Create new instance
        if not registration.enabled:
            return None
        
        instance = registration.source_class(config=registration.config)
        self._instances[name] = instance
        return instance
    
    def list_sources(self, enabled_only: bool = False) -> List[str]:
        """List registered source names.
        
        Args:
            enabled_only: Only return enabled sources
            
        Returns:
            List of source names
        """
        sources = list(self._registrations.keys())
        if enabled_only:
            return [name for name, reg in self._registrations.items() if reg.enabled]
        return sources
    
    def get_config(self, name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a source.
        
        Args:
            name: Name of the source
            
        Returns:
            Configuration dictionary, or None if not found
        """
        registration = self._registrations.get(name)
        return registration.config if registration else None
    
    def load_from_file(self, filepath: str) -> None:
        """Load source plugins from a Python file.
        
        Args:
            filepath: Path to Python file containing source classes
        """
        spec = importlib.util.spec_from_file_location("module.sources", filepath)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {filepath}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find all classes that inherit from BibliographicSource
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BibliographicSource) and obj is not BibliographicSource:
                self.register(obj)
    
    def load_from_directory(self, directory: str) -> None:
        """Load source plugins from a directory.
        
        Args:
            directory: Path to directory containing source plugin files
        """
        import os
        for filename in os.listdir(directory):
            if filename.endswith('.py') and not filename.startswith('_'):
                filepath = os.path.join(directory, filename)
                self.load_from_file(filepath)
    
    def from_config_dict(self, config: Dict[str, Any]) -> None:
        """Load sources from a configuration dictionary.
        
        Example config format:
        {
            "sources": {
                "crossref": {
                    "source_type": "crossref",
                    "enabled": true
                },
                "semantic_scholar": {
                    "source_type": "semantic_scholar",
                    "enabled": true,
                    "api_key": "..."
                }
            }
        }
        
        Args:
            config: Configuration dictionary
        """
        if 'sources' not in config:
            return

        for name, source_config in config['sources'].items():
            source_name = str(name)
            source_type = str(source_config.get('source_type', source_name))
            self.register(
                source_class=self._resolve_source_class(source_type),
                name=source_name,
                config=source_config
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry to dictionary.
        
        Returns:
            Dictionary representation of registry
        """
        return {
            name: {
                'enabled': reg.enabled,
                'config': reg.config
            }
            for name, reg in self._registrations.items()
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load registry from dictionary.
        
        Args:
            data: Dictionary representation of registry
        """
        for name, source_data in data.items():
            source_name = str(name)
            source_type = str(source_data.get('source_type', source_name))
            self.register(
                source_class=self._resolve_source_class(source_type),
                name=source_name,
                config=source_data.get('config', source_data)
            )
    
    def get_registered_sources(self) -> List[SourceRegistration]:
        """Get all registered source registrations.
        
        Returns:
            List of SourceRegistration objects
        """
        return list(self._registrations.values())

    def _resolve_source_class(self, source_type: str) -> Type[BibliographicSource]:
        normalized = source_type.strip().lower().replace('-', '_')
        if normalized in {'crossref', 'cross_ref'}:
            from citegeist.sources.crossref import CrossRefSource

            return CrossRefSource
        if normalized in {'opencitations', 'open_citations'}:
            from citegeist.sources.opencitations import OpenCitationsSource

            return OpenCitationsSource
        if normalized == 'unpaywall':
            from citegeist.sources.unpaywall import UnpaywallSource

            return UnpaywallSource
        if normalized in {'europepmc', 'europe_pmc'}:
            from citegeist.sources.europepmc import EuropePmcSource

            return EuropePmcSource
        if normalized in {'semanticscholar', 'semantic_scholar'}:
            from citegeist.sources.semanticscholar import SemanticScholarSource

            return SemanticScholarSource
        if normalized in {"openlibrary", "open_library"}:
            from citegeist.sources.openlibrary import OpenLibrarySource

            return OpenLibrarySource
        raise ValueError(f"Unknown source type: {source_type}")


# Global registry instance
_global_registry = SourceRegistry()


def get_registry() -> SourceRegistry:
    """Get the global source registry instance.
    
    Returns:
        The global SourceRegistry instance
    """
    return _global_registry
