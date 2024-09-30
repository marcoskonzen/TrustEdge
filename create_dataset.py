"""This script will be responsible for creating EdgeSimPy dataset files"""
# Importing Python libraries
from random import seed, sample
import json
import copy
import matplotlib.pyplot as plt
import networkx as nx

# Importing EdgeSimPy components
from edge_sim_py import *

def display_topology(topology: object, output_filename: str = "topology"):
    """Prints the network topology to an output file.

    Args:
        topology (object): Topology object.
        output_filename (str, optional): Output file name. Defaults to "topology".
    """
    # Customizing visual representation of topology
    positions = {}
    labels = {}
    colors = []
    sizes = []

    for node in topology.nodes():
        positions[node] = node.coordinates
        labels[node] = node.id
        node_size = (
            500
            if any(user.coordinates == node.coordinates for user in User.all())
            else 100
        )
        sizes.append(node_size)

        if (
            len(node.base_station.edge_servers)
            and sum(len(s.container_registries) for s in node.base_station.edge_servers)
            == 0
        ):
            node_server = node.base_station.edge_servers[0]
            if node_server.model_name == "PowerEdge R620":
                colors.append("green")
            elif node_server.model_name == "SGI":
                colors.append("red")

        elif (
            len(node.base_station.edge_servers)
            and sum(len(s.container_registries) for s in node.base_station.edge_servers)
            > 0
        ):
            colors.append("blue")
        else:
            colors.append("black")

    # Configuring drawing scheme
    nx.draw(
        topology,
        pos=positions,
        node_color=colors,
        node_size=sizes,
        labels=labels,
        font_size=6,
        font_weight="bold",
        font_color="whitesmoke",
    )

    # Saving a topology image in the disk
    plt.savefig(f"{output_filename}.png", dpi=120)

# Defining a seed value to enable reproducibility
seed(0)

# Creating list of map coordinates
map_coordinates = hexagonal_grid(x_size=4, y_size=4)

# Creating base stations for providing wireless connectivity to users and network switches for wired connectivity
for coordinates_id, coordinates in enumerate(map_coordinates):
    # Creating a base station object
    base_station = BaseStation()
    base_station.wireless_delay = 0
    base_station.coordinates = coordinates

    # Creating a network switch object using the "sample_switch()" generator, which embeds built-in power consumption specs
    network_switch = sample_switch()
    base_station._connect_to_network_switch(network_switch=network_switch)

# Creating a partially-connected mesh network topology
partially_connected_hexagonal_mesh(
    network_nodes=NetworkSwitch.all(),
    link_specifications=[
        {
            "number_of_objects": 33,
            "delay": 3,
            "bandwidth": 12.5,
            "transmission_delay": 0.06,  # Value in seconds
        },
    ],
)

SERVERS_PER_SPEC = 8
edge_server_specifications = [
    {
        "number_of_objects": SERVERS_PER_SPEC,
        "model_name": "PowerEdge R620",
        "cpu": 16,
        "memory": 24,
        "disk": 131072,  # 128 GB
        "static_power_percentage": 54.1 / 243,
        "max_power_consumption": 243,
    },
    {
        "number_of_objects": SERVERS_PER_SPEC,
        "model_name": "SGI",
        "cpu": 32,
        "memory": 32,
        "disk": 131072,  # 128 GB
        "static_power_percentage": 265 / 1387,
        "max_power_consumption": 1387,
    },
]

# Creating edge servers
for spec in edge_server_specifications:
    for _ in range(spec["number_of_objects"]):
        # Creating an edge server
        edge_server = EdgeServer()
        edge_server.model_name = spec["model_name"]

        # Computational capacity (CPU in number of cores, RAM in gigabytes, and disk in megabytes)
        edge_server.cpu = spec["cpu"]
        edge_server.memory = spec["memory"]
        edge_server.disk = spec["disk"]

        # Power-related attributes
        edge_server.power_model = LinearServerPowerModel
        edge_server.power_model_parameters = {
            "static_power_percentage": spec["static_power_percentage"],
            "max_power_consumption": spec["max_power_consumption"],
        }

        # Connecting the edge server to a random base station that has no edge server connected to it yet
        base_station = sample([base_station for base_station in BaseStation.all() if len(base_station.edge_servers) == 0], 1)[0]
        base_station._connect_to_edge_server(edge_server=edge_server)

display_topology(topology=Topology.first())