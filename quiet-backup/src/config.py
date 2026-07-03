from typing import Any, Dict
import argparse
import logging
import json



def parseArgs() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description='Periodic low-impact backup daemon.'
	)
	parser.add_argument(
		'--config',
		type=str,
		required=True,
		help='Path to JSON configuration file.'
	)
	parser.add_argument(
		'--state-file',
		type=str,
		help='Override path to JSON state file.'
	)
	parser.add_argument(
		'--min-interval-hours',
		type=int,
		help='Override minimum interval between runs (default 12h).'
	)
	parser.add_argument(
		'--spread-hours',
		type=int,
		help='Override spread period for backups (default 6h).'
	)
	parser.add_argument(
		'--initial-delay-minutes',
		type=int,
		help='Override initial delay before first run (default 10 min).'
	)
	parser.add_argument(
		'--scan-pause-ms',
		type=int,
		help='Override pause between scan filesystem calls in ms.'
	)
	parser.add_argument(
		'--max-files-per-minute',
		type=int,
		help='Override max backup rate (files per minute).'
	)
	parser.add_argument(
		'--run-once',
		action='store_true',
		help='Run a single cycle then exit.'
	)
	parser.add_argument(
		'--log-level',
		default='info',
		help='Set the log level'
	)

	return parser.parse_args()


def loadConfig(args: argparse.Namespace) -> Dict[str, Any]:
	with open(args.config, 'r', encoding='utf-8') as configFile:
		config = json.load(configFile)

	if args.state_file:
		config['state_file'] = args.state_file
	if args.min_interval_hours is not None:
		config['min_interval_hours'] = args.min_interval_hours
	if args.spread_hours is not None:
		config['spread_hours'] = args.spread_hours
	if args.initial_delay_minutes is not None:
		config['initial_delay_minutes'] = args.initial_delay_minutes
	if args.scan_pause_ms is not None:
		config['scan_pause_ms'] = args.scan_pause_ms
	if args.max_files_per_minute is not None:
		config['max_files_per_minute'] = args.max_files_per_minute

	if config['max_files_per_minute'] == 0:
		logging.warning("Config max_files_per_minute cannot be 0, setting it to the minimal value 1")
		config['max_files_per_minute'] = 1

	return config