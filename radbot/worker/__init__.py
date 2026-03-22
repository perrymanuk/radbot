"""RadBot session worker package.

Runs a headless A2A agent server as a Nomad batch job.
Each worker holds a single agent session in memory, surviving
main application restarts.
"""
