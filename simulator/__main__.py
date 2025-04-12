"""This file contains the main executable file within the project."""

# Importing Python libraries
from random import seed
import time
import argparse

# Importing EdgeSimPy components
from edge_sim_py import *

# Importing helper functions
from simulator.helper_functions import *
from simulator.extensions import *

# Importing Resource management policies
from simulator.algorithms import *


def load_edgesimpy_extensions():
    """Loads EdgeSimPy extensions"""
    # Loading the entity extensions
    EdgeServer.step = edge_server_step
    EdgeServer.failure_history = failure_history

    Application.step = application_step
    Application.availability_status = availability_status


def main(parameters: dict):
    # Defining a seed value to enable reproducible results
    seed(parameters["seed_value"])

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

    display_simulation_metrics(simulation_parameters=parameters, simulation_execution_time=final_time - start_time)


if __name__ == "__main__":
    # Parsing named arguments from the command line
    parser = argparse.ArgumentParser()

    # Generic arguments
    parser.add_argument("--seed", "-s", help="Seed value for EdgeSimPy", default="1")
    parser.add_argument("--input", "-i", help="Input dataset file", default="datasets/dataset1.json")
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
