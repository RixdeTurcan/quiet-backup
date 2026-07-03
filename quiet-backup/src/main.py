import logging
import sys
import time

from config import loadConfig, parseArgs
from backup import runOnce


def main() -> None:
	args = parseArgs()
	logging.basicConfig(
		level=args.log_level.upper(),
		format='%(asctime)s [%(levelname)s] %(message)s',
	)


	config = loadConfig(args)

	initialDelayM = int(config['initial_delay_minutes'])
	minIntervalH = int(config['min_interval_hours'])

	initialDelay = initialDelayM * 60
	minInterval = minIntervalH * 3600

	logging.info(
		'Periodic backup service starting (initial delay %i minutes, interval %i hours)',
		initialDelayM,
		minIntervalH,
	)

	if initialDelay > 0:
		logging.info('Sleeping for %i minutes before first run', initialDelayM)
		time.sleep(initialDelay)

	while True:
		t0 = time.time()
		runOnce(config)

		if args.run_once:
			logging.info('run-once requested, exiting')
			break

		tNext = t0 + minInterval
		t1 = time.time()
		dt = tNext - t1

		if dt > 0:
			logging.info('Sleeping for %i minutes before next run', dt/60)
			time.sleep(dt)





if __name__ == '__main__':
	try:
		main()

	except KeyboardInterrupt:
		logging.info('Interrupted by user, exiting.')
		sys.exit(0)

	except Exception as e:
		logging.error(e, exc_info=True)