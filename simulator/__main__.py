"""This file contains the main executable file within the project."""

# Importing Python libraries
from random import seed
import time
import argparse

# Importing EdgeSimPy components
from edge_sim_py import *
from edge_sim_py.components.service import *

# Importing helper functions
from simulator.helper_functions import *
from simulator.extensions import *

# Importing Resource management policies
from simulator.algorithms import *


def load_edgesimpy_extensions():
    """Loads EdgeSimPy extensions"""
    # Loading the entity extensions
    Service.step = service_step
    EdgeServer.step = edge_server_step
    Application.step = application_step
    User.step = user_step
    
    # Propriedades adicionais
    EdgeServer.failure_history = failure_history
    EdgeServer.available_history = available_history
    Application.availability_status = availability_status
    Application.availability_history = availability_history
    Application.downtime_history = downtime_history

  

def main(parameters: dict):
    # Defining a seed value to enable reproducible results
    seed(parameters["seed_value"])

    # Resetar contadores globais de SLA no início da simulação
    reset_all_counters()

    # Creating a Simulator object
    simulator = Simulator(
        tick_duration=1,
        tick_unit="seconds",
        stopping_criterion=lambda model: model.schedule.steps == parameters["time_steps"],
        resource_management_algorithm=eval(parameters["algorithm"]),
        resource_management_algorithm_parameters=parameters,
        dump_interval=float("inf"),
        logs_directory=f"logs",
        user_defined_functions=[BaseFailureGroupModel],
    )

    # Parsing simulation parameters
    parameters_string = f"timestamp={int(time.time())};dataset={parameters['dataset'].split('datasets/')[1].split('.json')[0]};"
    for key, value in parameters.items():
        if key != "dataset":
            parameter_divisor = "" if key == list(parameters.keys())[-1] else ";"
            parameters_string += f"{key}={value}{parameter_divisor}"
    simulator.output_file_name = parameters_string

    User.set_communication_path = user_set_communication_path
    Topology.collect = topology_collect

    # Initializing the simulated scenario
    simulator.initialize(input_file=parameters["dataset"])

    # Applying EdgeSimPy extensions
    load_edgesimpy_extensions()

    # Starting the simulation's execution time counter
    start_time = time.time()

    # Executing the simulation
    simulator.run_model()

    # Finishing the simulation's execution time counter
    final_time = time.time()

    metrics = Topology.first().collect()
    print(f"==== {parameters['algorithm']} ====")
    for metric, value in metrics.items():
        print(f"{metric}: {value}")

if __name__ == "__main__":
    # Parsing named arguments from the command line
    parser = argparse.ArgumentParser()

    # Generic arguments
    parser.add_argument("--seed", "-s", help="Seed value for EdgeSimPy", default="1")
    parser.add_argument("--input", "-i", help="Input dataset file", default="datasets/dataset_extended.json")
    parser.add_argument("--algorithm", "-a", help="Algorithm that will be executed", required=True)
    parser.add_argument("--time-steps", "-t", help="Number of time steps (seconds) to be simulated", required=True)

    args = parser.parse_args()

    parameters = {
        "seed_value": int(args.seed),
        "dataset": args.input,
        "algorithm": args.algorithm,
        "time_steps": int(args.time_steps),
    }

    main(parameters=parameters)
