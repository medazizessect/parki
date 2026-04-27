"""
Geographic Analysis with Folium Maps.

Generates interactive HTML maps showing camera positions, traffic
heat-maps, and route overlays.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import folium
from folium.plugins import HeatMap, MarkerCluster

from .config import MapConfig, get_settings

logger = logging.getLogger(__name__)


@dataclass
class CameraInfo:
    """Lightweight representation of a camera for map rendering."""

    camera_id: int
    name: str
    latitude: float
    longitude: float
    status: str = "active"
    vehicle_count: int = 0
    avg_speed: float = 0.0


@dataclass
class TrafficPoint:
    """Single traffic-density data point."""

    latitude: float
    longitude: float
    weight: float = 1.0


@dataclass
class RoutePoint:
    """A waypoint in a route overlay."""

    latitude: float
    longitude: float


class TrafficMapGenerator:
    """Builds Folium maps enriched with camera, heat-map, and route layers."""

    def __init__(self, config: Optional[MapConfig] = None) -> None:
        self._config = config or get_settings().map
        self._map: Optional[folium.Map] = None
        self._layers_added: list[str] = []

    # ------------------------------------------------------------------
    # Base map
    # ------------------------------------------------------------------
    def _create_base_map(self) -> folium.Map:
        """Create a Folium map centred on the configured location."""
        m = folium.Map(
            location=[self._config.center_lat, self._config.center_lng],
            zoom_start=self._config.zoom_level,
            tiles=self._config.tile_provider,
        )
        logger.debug(
            "Base map created at (%.4f, %.4f) zoom=%d",
            self._config.center_lat,
            self._config.center_lng,
            self._config.zoom_level,
        )
        return m

    @property
    def map(self) -> folium.Map:
        """Lazily initialise and return the underlying Folium map."""
        if self._map is None:
            self._map = self._create_base_map()
        return self._map

    # ------------------------------------------------------------------
    # Camera markers
    # ------------------------------------------------------------------
    def add_camera_markers(self, cameras_data: Sequence[CameraInfo]) -> None:
        """Add clustered markers for each camera.

        Each marker shows a popup with camera name, status, and vehicle count.
        """
        cluster = MarkerCluster(name="Cameras").add_to(self.map)

        for cam in cameras_data:
            icon_color = "green" if cam.status == "active" else "red"
            popup_html = (
                f"<b>{cam.name}</b><br>"
                f"Status: {cam.status}<br>"
                f"Vehicles: {cam.vehicle_count}<br>"
                f"Avg Speed: {cam.avg_speed:.1f} km/h"
            )
            folium.Marker(
                location=[cam.latitude, cam.longitude],
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=cam.name,
                icon=folium.Icon(color=icon_color, icon="video-camera", prefix="fa"),
            ).add_to(cluster)

        self._layers_added.append("camera_markers")
        logger.info("Added %d camera markers.", len(cameras_data))

    # ------------------------------------------------------------------
    # Traffic heat-map
    # ------------------------------------------------------------------
    def add_traffic_heatmap(self, traffic_data: Sequence[TrafficPoint]) -> None:
        """Add a heat-map overlay representing traffic density."""
        heat_data = [
            [pt.latitude, pt.longitude, pt.weight] for pt in traffic_data
        ]
        if not heat_data:
            logger.warning("No traffic data provided for heat-map.")
            return

        HeatMap(
            heat_data,
            name="Traffic Density",
            radius=20,
            blur=15,
            max_zoom=16,
        ).add_to(self.map)

        self._layers_added.append("traffic_heatmap")
        logger.info("Added traffic heat-map with %d points.", len(heat_data))

    # ------------------------------------------------------------------
    # Route overlay
    # ------------------------------------------------------------------
    def add_route_overlay(
        self,
        route_data: Sequence[RoutePoint],
        *,
        color: str = "blue",
        weight: int = 4,
        tooltip: str = "Suggested Route",
    ) -> None:
        """Draw a polyline route on the map."""
        if len(route_data) < 2:
            logger.warning("Route overlay requires at least 2 points.")
            return

        coords = [[pt.latitude, pt.longitude] for pt in route_data]
        folium.PolyLine(
            coords,
            color=color,
            weight=weight,
            opacity=0.8,
            tooltip=tooltip,
        ).add_to(self.map)

        self._layers_added.append("route_overlay")
        logger.info("Added route overlay with %d waypoints.", len(route_data))

    # ------------------------------------------------------------------
    # Complete report map
    # ------------------------------------------------------------------
    def generate_traffic_report_map(
        self,
        cameras: Sequence[CameraInfo] | None = None,
        traffic: Sequence[TrafficPoint] | None = None,
        routes: Sequence[Sequence[RoutePoint]] | None = None,
    ) -> folium.Map:
        """Build a complete map with all available layers.

        Parameters are optional; layers are added only when data is provided.
        """
        if cameras:
            self.add_camera_markers(cameras)
        if traffic:
            self.add_traffic_heatmap(traffic)
        if routes:
            for idx, route in enumerate(routes):
                self.add_route_overlay(route, tooltip=f"Route {idx + 1}")

        # Layer control so users can toggle overlays
        folium.LayerControl().add_to(self.map)
        logger.info("Traffic report map generated (layers: %s).", self._layers_added)
        return self.map

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_map(self, filename: str = "traffic_map.html") -> Path:
        """Save the map to an HTML file and return the path."""
        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        self.map.save(str(filepath))
        logger.info("Map saved to %s", filepath)
        return filepath

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Discard the current map so a fresh one is created on next access."""
        self._map = None
        self._layers_added.clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    gen = TrafficMapGenerator()

    sample_cameras = [
        CameraInfo(1, "Cam-01", -23.5505, -46.6333, "active", 1200, 42.5),
        CameraInfo(2, "Cam-02", -23.5600, -46.6400, "active", 980, 38.1),
        CameraInfo(3, "Cam-03", -23.5450, -46.6250, "inactive", 0, 0.0),
    ]
    sample_traffic = [
        TrafficPoint(-23.5505, -46.6333, 1200),
        TrafficPoint(-23.5600, -46.6400, 980),
        TrafficPoint(-23.5520, -46.6350, 750),
    ]
    sample_route = [
        RoutePoint(-23.5505, -46.6333),
        RoutePoint(-23.5520, -46.6350),
        RoutePoint(-23.5600, -46.6400),
    ]

    gen.generate_traffic_report_map(
        cameras=sample_cameras,
        traffic=sample_traffic,
        routes=[sample_route],
    )
    path = gen.save_map("demo_traffic_map.html")
    print(f"Demo map saved to {path}")
