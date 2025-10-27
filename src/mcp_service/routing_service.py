from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RouteNode:
    """Represents a routing node (intersection)"""

    id: int
    node_identifier: str
    connected_edges: Set[int]


@dataclass
class RouteEdge:
    """Represents a routing edge (road segment)"""

    id: int
    road_id: str
    road_name: Optional[str]
    source_node_id: int
    target_node_id: int
    cost: float
    reverse_cost: float
    geometry: Optional[Dict[str, Any]]


class InMemoryRoutingNetwork:
    """In-memory routing network built from OS NGD data"""

    def __init__(self):
        self.nodes: Dict[int, RouteNode] = {}
        self.edges: Dict[int, RouteEdge] = {}
        self.node_lookup: Dict[str, int] = {}
        self.is_built = False

    def add_node(self, node_identifier: str) -> int:
        """Add a node and return its internal ID"""
        if node_identifier in self.node_lookup:
            return self.node_lookup[node_identifier]

        node_id = len(self.nodes) + 1
        self.nodes[node_id] = RouteNode(
            id=node_id,
            node_identifier=node_identifier,
            connected_edges=set(),
        )
        self.node_lookup[node_identifier] = node_id
        return node_id

    def add_edge(self, road_data: Dict[str, Any]) -> None:
        """Add a road link as an edge"""
        properties = road_data.get("properties", {})

        start_node = properties.get("startnode", "")
        end_node = properties.get("endnode", "")

        if not start_node or not end_node:
            logger.warning(f"Road link {properties.get('id')} missing node data")
            return

        source_id = self.add_node(start_node)
        target_id = self.add_node(end_node)

        roadlink_id = None
        road_track_refs = properties.get("roadtrackorpathreference", [])
        if road_track_refs and len(road_track_refs) > 0:
            roadlink_id = road_track_refs[0].get("roadlinkid", "")

        edge_id = len(self.edges) + 1
        cost = properties.get("geometry_length", 100.0)

        edge = RouteEdge(
            id=edge_id,
            road_id=roadlink_id or "NONE",
            road_name=properties.get("name1_text"),
            source_node_id=source_id,
            target_node_id=target_id,
            cost=cost,
            reverse_cost=cost,
            geometry=road_data.get("geometry"),
        )

        self.edges[edge_id] = edge

        self.nodes[source_id].connected_edges.add(edge_id)
        self.nodes[target_id].connected_edges.add(edge_id)

    def get_connected_edges(self, node_id: int) -> List[RouteEdge]:
        """Get all edges connected to a node"""
        if node_id not in self.nodes:
            return []

        return [self.edges[edge_id] for edge_id in self.nodes[node_id].connected_edges]

    def get_summary(self) -> Dict[str, Any]:
        """Get network summary statistics"""
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "is_built": self.is_built,
            "sample_nodes": [
                {
                    "id": node.id,
                    "identifier": node.node_identifier,
                    "connected_edges": len(node.connected_edges),
                }
                for node in list(self.nodes.values())[:5]
            ],
        }

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes as a flat list"""
        return [
            {
                "id": node.id,
                "node_identifier": node.node_identifier,
                "connected_edge_count": len(node.connected_edges),
                "connected_edge_ids": list(node.connected_edges),
            }
            for node in self.nodes.values()
        ]

    def get_all_edges(self) -> List[Dict[str, Any]]:
        """Get all edges as a flat list"""
        return [
            {
                "id": edge.id,
                "road_id": edge.road_id,
                "road_name": edge.road_name,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "cost": edge.cost,
                "reverse_cost": edge.reverse_cost,
                "geometry": edge.geometry,
            }
            for edge in self.edges.values()
        ]


class OSRoutingService:
    """Service to build and query routing networks from OS NGD data"""

    def __init__(self, api_client):
        self.api_client = api_client
        self.network = InMemoryRoutingNetwork()
        self.raw_restrictions: List[Dict[str, Any]] = []

    async def _fetch_restriction_data(
        self,
        bbox: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch raw restriction data"""
        try:
            logger.debug("Fetching restriction data...")

            params = {
                "limit": min(limit, 100),
                "crs": "http://www.opengis.net/def/crs/EPSG/0/4326",
            }

            if bbox:
                params["bbox"] = bbox

            restriction_data = await self.api_client.make_request(
                "COLLECTION_FEATURES",
                params=params,
                path_params=["trn-rami-restriction-1"],
            )

            features = restriction_data.get("features", [])
            logger.debug(f"Fetched {len(features)} restriction features")

            return features

        except Exception as e:
            logger.error(f"Error fetching restriction data: {e}")
            return []

    async def build_routing_network(
        self,
        bbox: Optional[str] = None,
        limit: int = 1000,
        include_restrictions: bool = True,
    ) -> Dict[str, Any]:
        """Build the routing network from OS NGD road links with optional restriction data"""
        try:
            logger.debug("Building routing network from OS NGD data...")

            if include_restrictions:
                self.raw_restrictions = await self._fetch_restriction_data(bbox, limit)

            params = {
                "limit": min(limit, 100),
                "crs": "http://www.opengis.net/def/crs/EPSG/0/4326",
            }

            if bbox:
                params["bbox"] = bbox

            road_links_data = await self.api_client.make_request(
                "COLLECTION_FEATURES",
                params=params,
                path_params=["trn-ntwk-roadlink-4"],
            )

            features = road_links_data.get("features", [])
            logger.debug(f"Processing {len(features)} road links...")

            for feature in features:
                self.network.add_edge(feature)

            self.network.is_built = True

            summary = self.network.get_summary()
            logger.debug(
                f"Network built: {summary['total_nodes']} nodes, {summary['total_edges']} edges"
            )

            return {
                "status": "success",
                "message": f"Built routing network with {summary['total_nodes']} nodes and {summary['total_edges']} edges",
                "network_summary": summary,
                "restrictions": self.raw_restrictions if include_restrictions else [],
                "restriction_count": len(self.raw_restrictions)
                if include_restrictions
                else 0,
            }

        except Exception as e:
            logger.error(f"Error building routing network: {e}")
            return {"status": "error", "error": str(e)}

    def get_network_info(self) -> Dict[str, Any]:
        """Get current network information"""
        return {"status": "success", "network": self.network.get_summary()}

    def get_flat_nodes(self) -> Dict[str, Any]:
        """Get flat list of all nodes"""
        if not self.network.is_built:
            return {
                "status": "error",
                "error": "Routing network not built. Call build_routing_network first.",
            }

        return {"status": "success", "nodes": self.network.get_all_nodes()}

    def get_flat_edges(self) -> Dict[str, Any]:
        """Get flat list of all edges with connections"""
        if not self.network.is_built:
            return {
                "status": "error",
                "error": "Routing network not built. Call build_routing_network first.",
            }

        return {"status": "success", "edges": self.network.get_all_edges()}

    def get_routing_tables(self) -> Dict[str, Any]:
        """Get both nodes and edges as flat tables"""
        if not self.network.is_built:
            return {
                "status": "error",
                "error": "Routing network not built. Call build_routing_network first.",
            }

        return {
            "status": "success",
            "nodes": self.network.get_all_nodes(),
            "edges": self.network.get_all_edges(),
            "summary": self.network.get_summary(),
            "restrictions": self.raw_restrictions,
        }
