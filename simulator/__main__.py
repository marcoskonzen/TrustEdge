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
    """Executa a simulação com os parâmetros fornecidos."""
    
    # ✅ VALIDAÇÃO: Mostrar parâmetros recebidos
    print(f"\n{'='*70}")
    print(f"PARÂMETROS DA SIMULAÇÃO")
    print(f"{'='*70}")
    print(f"  Algoritmo: {parameters.get('algorithm', 'N/A')}")
    print(f"  Seed: {parameters.get('seed', 'N/A')}")
    print(f"  Time Steps: {parameters.get('time_steps', 'N/A')}")
    print(f"  Dataset: {parameters.get('dataset', 'N/A')}")
    
    # ✅ Mostrar parâmetros específicos do algoritmo
    if parameters.get('algorithm') == 'trust_edge_v3':
        print(f"\n  TrustEdge V3 Parâmetros:")
        print(f"    - Window Size: {parameters.get('window_size', 'N/A')}")
        print(f"    - Reliability Threshold: {parameters.get('reliability_threshold', 'N/A')}%")
        print(f"    - Delay Threshold: {parameters.get('delay_threshold', 'N/A')}x")
        print(f"    - Run ID: {parameters.get('run_id', 'N/A')}")
    
    if parameters.get('algorithm') == 'kubernetes_inspired':
        print(f"\n  Kubernetes Enhancements:")
        print(f"    - P2P Layer Download: {'ENABLED ✅' if parameters.get('enable_p2p') else 'DISABLED ❌'}")
        print(f"    - Live Migration: {'ENABLED ✅' if parameters.get('enable_live_migration') else 'DISABLED ❌'}")
        print(f"    - Proactive SLA Migration: {'ENABLED ✅' if parameters.get('enable_proactive_sla_migration') else 'DISABLED ❌'}")
    
    print(f"{'='*70}\n")
    
    # Definir seed para reprodutibilidade
    seed(int(parameters["seed"]))

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

    # ✅ Armazenar parâmetros no modelo APÓS inicialização
    topology = Topology.first()
    if topology:
        model = topology.model
        model._sensitivity_params = {
            'window_size': parameters.get('window_size'),
            'reliability_threshold': parameters.get('reliability_threshold'),
            'delay_threshold': parameters.get('delay_threshold'),
            'run_id': parameters.get('run_id'),
        }
        model._kubernetes_config = {
            'enable_p2p': parameters.get('enable_p2p', False),
            'enable_live_migration': parameters.get('enable_live_migration', False),
        }

    # Applying EdgeSimPy extensions
    load_edgesimpy_extensions()

    # Starting the simulation's execution time counter
    start_time = time.time()

    # Executing the simulation
    simulator.run_model()

    # Finishing the simulation's execution time counter
    final_time = time.time()

    # Calcular e armazenar duração
    execution_time_seconds = final_time - start_time
    execution_time_minutes = execution_time_seconds / 60.0
    
    # Armazenar no modelo para acesso posterior
    Topology.first().model._simulation_execution_time_seconds = execution_time_seconds
    Topology.first().model._simulation_execution_time_minutes = execution_time_minutes

    metrics = Topology.first().collect()
    print(f"\n{'='*70}")
    print(f"MÉTRICAS FINAIS - {parameters['algorithm'].upper()}")
    print(f"{'='*70}")
    for metric, value in metrics.items():
        print(f"{metric}: {value}")
    
    # Imprimir tempo de execução
    print(f"\n{'='*70}")
    print(f"TEMPO DE EXECUÇÃO DA SIMULAÇÃO")
    print(f"{'='*70}")
    print(f"Duração: {execution_time_minutes:.2f} minutos ({execution_time_seconds:.2f} segundos)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    # Parsing named arguments from the command line
    parser = argparse.ArgumentParser(
        description="EdgeSimPy Simulator - TrustEdge V3 & Kubernetes Comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # TrustEdge V3 (baseline)
  python -m simulator --algorithm trust_edge_v3 --seed 12345 --time-steps 1500 \\
    --input datasets/dataset_extended.json --window-size 30 --reliability-threshold 80
  
  # Kubernetes (baseline)
  python -m simulator --algorithm kubernetes_inspired --seed 12345 --time-steps 1500 \\
    --input datasets/dataset_extended.json
  
  # Kubernetes + P2P
  python -m simulator --algorithm kubernetes_inspired --seed 12345 --time-steps 1500 \\
    --input datasets/dataset_extended.json --enable-p2p
  
  # Kubernetes + P2P + Live Migration
  python -m simulator --algorithm kubernetes_inspired --seed 12345 --time-steps 1500 \\
    --input datasets/dataset_extended.json --enable-p2p --enable-live-migration
        """
    )

    # Generic arguments
    parser.add_argument("--seed", "-s", help="Seed value for EdgeSimPy", default="1")
    parser.add_argument("--input", "-i", help="Input dataset file", default="datasets/dataset_extended.json")
    parser.add_argument("--algorithm", "-a", help="Algorithm that will be executed", required=True)
    parser.add_argument("--time-steps", "-t", help="Number of time steps (seconds) to be simulated", required=True)
    
    # TrustEdge V3 specific arguments
    parser.add_argument("--run-id", type=int, default=None, help="Run ID for sensitivity analysis")
    parser.add_argument("--window-size", type=int, default=10, help="TrustEdge: Window size for Weibull estimation")
    parser.add_argument("--reliability-threshold", type=float, default=95.0, help="TrustEdge: Reliability threshold (%%)")
    parser.add_argument("--delay-threshold", type=float, default=1.0, help="TrustEdge: Maximum delay multiplier")
    
    # Kubernetes enhancement arguments
    parser.add_argument("--enable-p2p", action="store_true", help="Kubernetes: Enable P2P layer download")
    parser.add_argument("--enable-live-migration", action="store_true", help="Kubernetes: Enable live migration")
    parser.add_argument(
    "--enable-proactive-sla-migration",
    action="store_true",
    help="Enable proactive migration on SLA violation (for kubernetes_inspired)")
    parser.add_argument(
    "--enable-failure-prediction",
    action="store_true",
    help="Enable Weibull failure prediction (for kubernetes_inspired)")
    
    
    args = parser.parse_args()

    parameters = {
        "dataset": args.input,
        "algorithm": args.algorithm,
        "seed": int(args.seed),
        "time_steps": int(args.time_steps),
        "window_size": args.window_size,
        "reliability_threshold": args.reliability_threshold,
        "delay_threshold": args.delay_threshold,
        "run_id": args.run_id,
        "enable_p2p": args.enable_p2p,
        "enable_live_migration": args.enable_live_migration,
        "enable_proactive_sla_migration": args.enable_proactive_sla_migration,
        "enable_failure_prediction": args.enable_failure_prediction,
    }

    main(parameters=parameters)