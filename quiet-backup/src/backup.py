from typing import Any, Dict, List
from pathlib import Path
import glob
import logging
import json
import time
import copy
import gzip
from datetime import datetime, timezone
import shutil
import os



def loadJson(path: Path, default: Any) -> Any:
	if not path.exists():
		return default
	try:
		with path.open('r', encoding='utf-8') as f:
			return json.load(f)
	except Exception as e:
		logging.error('Failed to read JSON from %s: %s', path, e)
		return default


def scanGroup(group: Dict[str, Any], state: Dict[str, Any], scanPauseDuration: float) -> List:
	groupName = group['name']
	filesToBackup = {}

	t = time.time()

	for pathCfg in group['paths']:
		logging.info("Scanning pattern: %s : %s > %s", pathCfg['base'], pathCfg['search'], pathCfg['dest'])
		basePath = Path(pathCfg['base'])

		count = 0

		for p in glob.iglob(pathCfg['search'].lstrip("/"), root_dir=basePath, recursive=True, include_hidden=True):
			fullPath = basePath.joinpath(p)

			if fullPath.is_dir():
				continue

			fullPathStr = str(fullPath)

			if not fullPathStr in state[groupName]:
				state[groupName][fullPathStr] = {
					'relPath': p,
					'size': 0,
					'date': 0,
					'dest': pathCfg['dest']
				}

			pathState = state[groupName][fullPathStr]

			if t < pathState['date'] + group['backup_policy']['min_delay_before_backup']*3600:
				continue

			stats = fullPath.stat()
			fileSize = round(stats.st_size)
			fileDate = round(stats.st_mtime)

			if pathState['date'] != fileDate or pathState['size'] != fileSize or pathState['dest'] != pathCfg['dest'] or pathState['relPath'] != p:
				logging.debug("File changed: %s", fullPathStr)

				pathState['date'] = fileDate
				pathState['size'] = fileSize
				pathState['relPath'] = p
				pathState['dest'] = pathCfg['dest']
				filesToBackup[fullPathStr] = True
				count += 1

			time.sleep(scanPauseDuration)

		logging.info('Found %i updated files', count)

	return filesToBackup.keys()

def mkdir775(path: Path):
	path.mkdir(parents=True, exist_ok=True)
	for p in [path, *path.parents]:
		if p.exists():
			try:
				p.chmod(0o775)
			except PermissionError:
				pass

def saveFile(dest: Dict[str, Any], policy: Dict[str, Any], fileState: Dict[str, Any], filePath: str, destBasePath: Path, timestamp: str) -> None:
	relPath = Path(fileState['relPath'])
	elems = relPath.name.split('.')

	compress = policy['compress']

	if policy['max_backups_per_file'] == 1:
		elems0Search = elems[0]

	else:
		elems0Search = '__*__{1}'.format(timestamp, elems[0])
		elems[0] = '__{0}__{1}'.format(timestamp, elems[0])

	if elems[-1].lower() in policy['compress_ignore_filetype']:
		compress = False

	if compress:
		elems.append('gz')

	relPath = relPath.parent.joinpath('.'.join(elems))
	elems[0] = elems0Search
	searchPath = relPath.parent.joinpath('.'.join(elems))

	destFullPath = Path(destBasePath.joinpath(fileState['dest']).joinpath(relPath))
	destFullSearchPath = Path(destBasePath.joinpath(fileState['dest']).joinpath(searchPath))

	logging.debug('Creating %s backup: %s > %s', dest['type'], filePath, destFullPath)
	if dest['type'] == 'local':
		try:
			mkdir775(destFullPath.parent)
		except PermissionError as e:
			logging.error('Incorrect permissions to create parent directory of: {}'.format(destFullPath))
			logging.error(e)
			return False

		try:
			if compress:
				with open(filePath, 'rb') as fIn:
					with gzip.open(destFullPath, 'wb', policy['compression_level']) as fOut:
						shutil.copyfileobj(fIn, fOut)

			else:
				shutil.copy2(filePath, destFullPath)

			destFullPath.chmod(0o775)

		except PermissionError as e:
			logging.error('Incorrect permissions to backup file: {}'.format(destFullPath))
			logging.error(e)
			return False


		if policy['max_backups_per_file'] > 1:
			backupFiles = sorted(glob.glob(str(destFullSearchPath), include_hidden=True))
			nbBackupFiles = len(backupFiles)

			if nbBackupFiles > policy['max_backups_per_file']:
				nbToDelete = nbBackupFiles - policy['max_backups_per_file']
				logging.debug('Found %i backups, deleting the %i oldests', nbBackupFiles, nbToDelete)
				for file in backupFiles[:nbToDelete]:
					logging.debug('Deleting old backup: %s', file)
					Path(file).unlink(missing_ok=True)

	return True



def backupGroup(group: Dict[str, Any], files: List[str], copyDuration: float, state: Dict[str, Any], statePath: Path, stateToUpdate: Dict[str, Any]) -> None:
	groupName = group['name']
	policy = group['backup_policy']
	timestamp = datetime.now(tz=timezone.utc).strftime("%Y_%m_%d_T_%H_%M_%S_Z")

	logging.info('Backing up %i files', len(files))


	for filePath in files:
		t0 = time.time()

		saved = True
		for dest in group['destinations']:
			destBasePath = Path(dest['path'])

			if dest['type'] not in ['local']:
				logging.warning('Unsuported destination type: %s', dest['type'])
				continue

			fileState = state[groupName][filePath]
			if not saveFile(dest, policy, fileState, filePath, destBasePath, timestamp):
				saved = False
				break

		if not saved:
			continue

		stateToUpdate[groupName][filePath] = state[groupName][filePath]
		tmpPath = statePath.parent.joinpath('state.json.tmp')
		with open(tmpPath, 'w', encoding='utf-8') as stateFile:
			json.dump(stateToUpdate, stateFile, indent=2)
			stateFile.flush()
			os.fsync(stateFile.fileno())
		tmpPath.replace(statePath)

		t1 = time.time()
		dt = t1 - t0
		if dt < copyDuration:
			time.sleep(copyDuration-dt)




def runOnce(config: Dict[str, Any]) -> None:
	statePath = Path(config['state_file'])
	scanPauseDuration = int(config['scan_pause_ms']) * 0.001
	spreadDuration = int(config['spread_hours']) * 3600
	targetCopyDuration = 60 / int(config['max_files_per_minute'])

	logging.info('Loading state from %s', statePath)
	state = loadJson(statePath, default={})
	stateToUpdate = copy.deepcopy(state)
	fileDataToBackup = {}

	logging.info('Starting backup run')

	count = 0

	for group in config['patterns']:
		groupName = group['name']
		if not groupName in state:
			state[groupName] = {}
			stateToUpdate[groupName] = {}

		logging.info('Scanning group: %s', groupName)

		files = scanGroup(group, state, scanPauseDuration)
		fileDataToBackup[groupName] = {
			'group': group,
			'files': files
		}
		l = len(files)
		count += len(files)

	copyDuration = min(spreadDuration/max(count, 1), targetCopyDuration)

	for groupName in fileDataToBackup:
		fileData = fileDataToBackup[groupName]
		groupName = fileData['group']['name']
		logging.info('Starting group backup: %s', groupName)
		backupGroup(fileData['group'], fileData['files'], copyDuration, state, statePath, stateToUpdate)
