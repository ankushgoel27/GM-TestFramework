import re
import argparse
import subprocess
import time
import logging
import requests
import zipfile
import io
import random
import os
import winreg
import json
import shutil
import yaml
import socket

# DON'T CHANGE THESE (use external config file instead)
DEFAULT_CONFIG = {
    "Launcher.accessKey": None,
    "Launcher.userFolder": None,
    "Launcher.runtimeVersion": None,
    "Launcher.html5Runner": None,

    "Launcher.runners": "vm",
    "Launcher.targets": "windows|Local",
    "Launcher.feed": "https://gms.yoyogames.com/Zeus-Runtime-Nocturnus-I.rss",
    "Launcher.project": "projects\\xUnit\\xUnit.yyp",

    "Server.port": 8080,
    "Server.endpoint": "tests",

    "Logger.level": 10,

    "$$parameters$$.isSandboxed": True
}

REDACTED_WORDS = ['-ak=', 'accessKey']
REDACTED_MESSAGE = "<redacted to prevent exposure of sensitive data>"

VALID_PLATFORMS = ['windows', 'mac', 'linux', 'android', 'ios', 'ipad', 'tvos', 'HTML5']
VALID_RUNNERS = ['vm', 'yyc']

FAILURE_MESSAGE = '[ERROR] Not all unit tests succeeded.'

IGOR_URL = 'https://gms.yoyogames.com/igor_win-x64.zip'

DRIVER_DETECT_BASE_URL = 'https://chromedriver.storage.googleapis.com/LATEST_RELEASE_'
DRIVER_DOWNLOAD_BASE_URL = 'https://chromedriver.storage.googleapis.com/'

ROOT_DIR = os.path.abspath('.')

USER_DIR = os.path.join(ROOT_DIR, 'user')
PROJECTS_DIR = os.path.join(ROOT_DIR, 'projects')
WORKSPACE_DIR = os.path.join(ROOT_DIR, 'workspace')

IGOR_DIR = os.path.join(WORKSPACE_DIR, 'igor')
CACHE_DIR = os.path.join(WORKSPACE_DIR, 'cache')
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, 'output', 'test.win')
RUNTIME_DIR = os.path.join(WORKSPACE_DIR, 'runtime')

FAIL_PATH = os.path.join(WORKSPACE_DIR, '.fail')
META_PATH = os.path.join(WORKSPACE_DIR, '.meta')

LOG_PATH = os.path.join(WORKSPACE_DIR, 'test_0.log')
RESULTS_PATH = os.path.join(WORKSPACE_DIR, 'results.json')

IGOR_PATH = os.path.join(IGOR_DIR, 'igor.exe')

SANDBOXED_PLATFORMS = ['windows', 'mac', 'linux']

def configure_logging(level=logging.INFO, format='%(asctime)s [%(levelname)s]: %(message)s', datefmt='%Y-%m-%d %H:%M:%S'):

    # Remove all handlers associated with the root logger object.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    class MaskSensitiveInfoFilter(logging.Filter):
        def filter(self, record):
            # Check if the log record contains sensitive information
            if any(key in record.getMessage() for key in REDACTED_WORDS):
                # If it does, redact the password
                record.msg = record.msg.replace(record.getMessage(), REDACTED_MESSAGE)
            return True

    # Create a console handler and add it to the root logger
    console_handler = logging.StreamHandler()
    logging.getLogger().addHandler(console_handler)

    # Set the log level
    logging.getLogger().setLevel(level)

    # Apply settings
    formatter = logging.Formatter(format, datefmt)
    console_handler.setFormatter(formatter)

    # Add the filter to the console handler
    console_handler.addFilter(MaskSensitiveInfoFilter())

def copy_file(src, dst):
    try:
        logging.info(f'Copying file from {src} to {dst}')
        shutil.copy2(src, dst)
        logging.info(f'File copied successfully')
    except Exception as e:
        logging.error(f'An error occurred while copying the file: {e}')
    
    return dst

def copy_folder(src, dest, contents_only=False):
    if not os.path.exists(src):
        logging.error(f"Source folder '{src}' does not exist or is not accessible.")
        return

    if not os.path.isdir(src):
        logging.error(f"Source '{src}' is not a folder.")
        return

    # Make sure the destination folder exists
    os.makedirs(dest, exist_ok=True)

    try:
        if contents_only:
            # Copy only the contents of the source folder
            for item in os.listdir(src):
                item_path = os.path.join(src, item)
                if os.path.isdir(item_path):
                    shutil.copytree(item_path, os.path.join(dest, item), dirs_exist_ok=True)
                else:
                    shutil.copy2(item_path, dest)
        else:
            # Copy the folder and its content
            shutil.copytree(src, os.path.join(dest, os.path.basename(src)), dirs_exist_ok=True)

        logging.info(f"Copied {'contents of' if contents_only else 'folder'} '{src}' to '{dest}'.")
    except Exception as e:
        logging.error(f"Failed to copy {'contents of' if contents_only else 'folder'} '{src}' to '{dest}': {e}")
    
    return dest

def remove_directory(directory):
    if os.path.exists(directory):
        try:
            shutil.rmtree(directory)
            logging.info(f'Successfully removed directory: {directory}')
        except OSError as e:
            logging.error(f'Error removing directory: {directory}')
            logging.error(e)
    else:
        logging.warning(f'Directory does not exist: {directory}')

def ensure_directories_exist(directories):
    for directory in directories:
        if not os.path.exists(directory):
            logging.info(f'Creating directory: {directory}')
            os.makedirs(directory)
        else:
            logging.info(f'Directory already exists: {directory}')

def change_directory(path):
    logging.info(f'Changing directory to {path}')
    try:
        os.chdir(path)
        logging.info(f'Successfully changed directory to {os.getcwd()}')
    except Exception as e:
        logging.error(f'Failed to change directory: {e}')

def download_and_extract(url, extract_path):
    # Download the file
    logging.info('Downloading file from URL: %s', url)
    response = requests.get(url)
    logging.info('Download complete')

    # Open the file in memory
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        # Extract the file to the specified path
        logging.info('Extracting file to: %s', extract_path)
        zf.extractall(extract_path)
        logging.info('Extraction complete')

def run_exe(exe_path, args):
    logging.info(f'Running {exe_path} with arguments {args}')
    process = subprocess.Popen([exe_path] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout_output = ''

    # Don't print the level
    configure_logging(format='%(asctime)s %(message)s')
    while True:
        stdout_line = process.stdout.readline().decode('utf-8')
        if not stdout_line and process.poll() is not None:
            break
        stripped_output = stdout_line.strip()
        if stripped_output != '':
            stdout_output += stdout_line
            logging.info(stripped_output)
    
    # Return logger to default configuration
    configure_logging()
    logging.info(f'Process completed')
    return stdout_output

def query_url(url):
    logging.info(f'Querying URL: {url}')
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            logging.error(f'Error querying URL {url}: {response.status_code}')
    except Exception as e:
        logging.error(f'Error querying URL {url}: {str(e)}')
    return None

def load_json_file(file_path):
    logging.info(f'Loading JSON file: {file_path}')
    try:
        with open(file_path, 'r') as file:
            data = yaml.safe_load(file.read())
            logging.info(f'JSON file loaded successfully')
            return data
    except FileNotFoundError:
        logging.error(f'JSON file not found: {file_path}')
    except json.JSONDecodeError as error:
        logging.error(f'Error decoding JSON file: {error}')
    return None

def save_to_json_file(obj, file_path):
    logging.info(f'Saving object to {file_path}')
    try:
        with open(file_path, 'w') as f:
            json.dump(obj, f, indent=4)
        logging.info(f'Object saved successfully to {file_path}')
    except Exception as e:
        logging.error(f'Error while saving object to {file_path}: {e}')

def parse_arguments(defaults):

    def merge_dictionaries(new, base):
        output = base.copy()
        for key, value in new.items():
            if key in base:
                logging.info(f'Overriding value for key {key}: {base[key]} -> {value}')
            output[key] = value
        return output

    # Auxiliary function that validates a list of targets (platform|device,platform|device,...)
    def validate_targets(input):
        # Regular expression pattern to match the input string format
        pattern = r'^(' + '|'.join(VALID_PLATFORMS) + r')\|[\w\s\.\-_%@&]+(,(' + '|'.join(VALID_PLATFORMS) + r')\|[\w\s\.\-_%@&]+)*$'
        # Check if the input string matches the pattern
        match = re.match(pattern, input)
        if not match:
            raise argparse.ArgumentTypeError(f'Invalid -t/--t format (follow the format "<PLATFORM>|<DEVICE>,<PLATFORM>|<DEVICE>,..." supported platforms: {VALID_PLATFORMS})')
        
        # Split each key-value pair by the pipe character "|" to separate the key and value
        return [(pair.split('|')[0], pair.split('|')[1]) for pair in input.split(',')]

    # Auxiliary function that validates a list of runners (runner,runner,...)
    def validate_runners(input):
        # Regular expression pattern to match the input string format
        pattern = r'^(' + '|'.join(VALID_RUNNERS) + r')(,(' + '|'.join(VALID_RUNNERS) + r'))*$'
        # Check if the input string matches the pattern
        match = re.match(pattern, input)
        if not match:
            raise argparse.ArgumentTypeError(f'Invalid -r/--r format (follow the format "<RUNNER>,<RUNNER>,..." supported runners are: {VALID_RUNNERS})')
        
        # Split each key-value pair by the pipe character "|" to separate the key and value
        return list(map(str.upper, input.split(',')))

    # Auxiliary function that validates a runtime version
    def validate_version(input):
        pattern = re.compile(r'^\d+\.\d+\.\d+\.\d+$')
        if not pattern.match(input):
            raise argparse.ArgumentTypeError('Invalid version format. Use <Major>.<Minor>.<Build>.<Revision>')
        return input

    # Auxiliary function that validates an existing path
    def validate_path(input):    
        resolved_path = os.path.abspath(input)
        if not os.path.exists(resolved_path):
            raise argparse.ArgumentTypeError(f'Invalid path provided. This path can be relative or absolute but must exist.')
        return resolved_path

    # Auxiliary function that will make sure the arg exists (either from command line or from config file)
    def ensure_argument(args, path, parsed_args, name, param, validator = None):
        if not args[path]:
            if not getattr(parsed_args, name):
                parser.error(f"argument -{param}/--{param} is required or should be passed from config file (-cf/--cf) as: '{path}'")
            value = getattr(parsed_args, name)
            args[path] = value
        if validator:
            args[path] = validator(args[path])

    parser = argparse.ArgumentParser(description='Run hybrid framework')

    default_targets = defaults['Launcher.targets']
    default_runners = defaults['Launcher.runners']
    default_feed = defaults['Launcher.feed']

    parser.add_argument('-t', '--targets', type=validate_targets, required=False, help=f'A comma separated list of "platform|config" pairs to run the framework on (defaults <{default_targets}>)')
    parser.add_argument('-r', '--runners', type=validate_runners, required=False, help=f'Runner(s) to run the test on (defaults <{default_runners}>)')
    parser.add_argument('-f', '--feed', type=str, required=False, help=f'RSS feed to use (defaults to <{default_feed}>)')
    parser.add_argument('-uf', '--userFolder', type=validate_path, required=False, help='The path to the GameMaker\' user folder')
    parser.add_argument('-ak', '--accessKey', type=str, required=False, help='The access key to download GameMaker\'s license')
    parser.add_argument('-cf', '--configFile', type=validate_path, required=False, help='The config file to be used by the launcher')
    parser.add_argument('-rv', '--runtimeVersion', type=validate_version, default=None, help='Runner version to use (defaults to <latest>)')
    parser.add_argument('-h5r', '--html5Runner', type=validate_path, required=False, help='A custom HTML5 runner to use instead of the runtime one')

    parsed_args = parser.parse_args()

    # Arguments are considered the default to beging with
    args = defaults.copy()

    # Load data from config file (if there is one)
    if parsed_args.configFile:
        config = load_json_file(parsed_args.configFile)
        args = merge_dictionaries(config, defaults)

    ensure_argument(args, 'Launcher.targets', parsed_args, 'targets', 't', validate_targets)
    ensure_argument(args, 'Launcher.runners', parsed_args, 'runners', 'r', validate_runners)
    ensure_argument(args, 'Launcher.feed', parsed_args, 'feed', 'f')
    ensure_argument(args, 'Launcher.userFolder', parsed_args, 'userFolder', 'uf', validate_path)
    ensure_argument(args, 'Launcher.accessKey', parsed_args, 'accessKey', 'ak')

    return args

def check_file_exists(file_path):
    if os.path.exists(file_path):
        logging.info(f"File '{file_path}' exists")
        return True
    else:
        logging.warning(f"File '{file_path}' does not exist")
        return False

def get_local_ip_address():
    # Get the hostname
    hostname = socket.gethostname()

    # Get the IP address for the hostname
    try:
        ip_address = socket.gethostbyname(hostname)
        logging.info(f"Local IP address: {ip_address}")
        return ip_address
    except socket.gaierror:
        logging.error("Failed to retrieve local IP address")
        return None

# Igor

def igor_get_license(access_key, output_path):
    run_exe(IGOR_PATH, [f'-ak={access_key}', f'-of={output_path}', 'Runtime', 'FetchLicense'])

def igor_get_runtime_version(user_folder, feed, version):
    # This will prevent browser cache
    cacheBust = random.randint(111111111, 999999999)
    # Setup arguments
    args = [f'/uf={user_folder}', f'/ru={feed}?cachebust={cacheBust}', 'Runtime', 'Info']
    if version:
        args.append(version)
    
    # Execute command
    result = run_exe(IGOR_PATH, args)

    pattern = re.compile(r'Version (\d+\.\d+\.\d+\.\d+)')
    match = pattern.search(result)
    if match:
        version = match.group(1)
        return version
    else:
        return None

def igor_install_runtime(user_folder, feed, version, platforms):
    # This will prevent browser cache
    cacheBust = random.randint(111111111, 999999999)
    # Prepare modules string
    modules = ','.join(platforms).lower()
    # Setup arguments
    args = [f'/uf={user_folder}', f'/ru={feed}?cachebust={cacheBust}', f'/rp={RUNTIME_DIR}', f'/m={modules}', 'Runtime', 'Install', version]
    
    # Execute command
    run_exe(IGOR_PATH, args)

    return os.path.join(RUNTIME_DIR, f'runtime-{version}')

def igor_run_tests(igor_path, project_file, user_folder, runtime_path, targets, runner = None, verbosity_level = 4):

    # Setup verbosity level
    args = []
    for _ in range(verbosity_level):
        args.append('/v')
    # Setup arguments
    args += [f'/uf={user_folder}', f'/rp={runtime_path}', f'/cache={CACHE_DIR}', f'/of={OUTPUT_DIR}', f'/target={targets}']
    if runner != None:
        args += [f'/r={runner}']
    # Setup command
    args += ['Tests', 'RunTests', project_file]

    # Execute command (change working directory)
    change_directory(WORKSPACE_DIR)
    run_exe(igor_path, args)
    change_directory(ROOT_DIR)

# HTML5 Specific

def download_chrome_driver(runtime_path):

    # Get Chrome version
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Google Chrome')
        chrome_version = winreg.QueryValueEx(key, 'Version')[0]
    except:
        logging.error(f'Unable to find Chrome version')
        return None

    # Compute relevate version (extract W.X.Y from W.X.Y.Z)
    relevant_version = chrome_version
    match = re.search(r'\d+\.\d+\.\d+', chrome_version)
    if match:
        relevant_version = match.group()
        logging.info(f'Relevant Chrome version: {relevant_version}')
    else:
        logging.error(f'Could not extract relevat Chrome version from {chrome_version}')
        return None

    # Get Chrome driver version
    driver_version_url = f'{DRIVER_DETECT_BASE_URL}{relevant_version}'
    driver_version = query_url(driver_version_url)

    if driver_version == None:
        return None
    
    # Build download link
    version_url = f'{driver_version}/chromedriver_win32.zip'
    download_url = DRIVER_DOWNLOAD_BASE_URL + version_url

    # Download and extract the driver
    extract_path = os.path.join(runtime_path, 'bin', 'igor', 'windows', 'x64')
    download_and_extract(download_url, extract_path)

    # Return 'chromedriver.exe' path
    return os.path.join(extract_path, 'chromedriver.exe')

# Android Specific

def start_android_emulator(sdk_path):

    # Get 'emulator' and 'adb' paths
    emulator_path = os.path.join(sdk_path, 'emulator', 'emulator.exe')
    adb_path = os.path.join(sdk_path, 'platform-tools', 'adb.exe')

    # Get emulators list
    avd_list = subprocess.run([emulator_path, '-list-avds'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    avds = avd_list.stdout.decode().strip().splitlines()

    if len(avds) == 0:
        logging.error('No Android Virtual Devices found.')
        return None

    # Start running the first emulator available
    emulator_name = avds[0]
    logging.info(f"Starting AVD: {emulator_name}")
    with open(os.devnull, "w") as f:
        subprocess.Popen([emulator_path, '-avd', emulator_name], stdout=f, stderr=f)
    logging.info('Emulator started')

    # Wait for the emulator to fully boot
    logging.info('Waiting for emulator to fully boot')
    boot_check = subprocess.run([adb_path, 'shell', 'getprop', 'sys.boot_completed'], capture_output=True)
    while boot_check.stdout.strip() != b'1':
        time.sleep(1)
        boot_check = subprocess.run([adb_path, 'shell', 'getprop', 'sys.boot_completed'], capture_output=True)
    logging.info('Emulator is fully booted')

    #Return the emulator id number
    result = subprocess.check_output([adb_path, 'devices'], shell=True).decode("utf-8")
    lines = result.strip().split("\n")[1:]
    emulators = [line.split("\t")[0] for line in lines if "emulator" in line]
    if len(emulators) == 0:
        logging.error('No running emulators found.')
        return None
    else:
        emulator_id = emulators[0]
        logging.info(f'Running emulator id: {emulator_id}')
        return emulator_id

def stop_android_emulator(sdk_path):
    # Stop the emulator
    adb_path = os.path.join(sdk_path, 'platform-tools', 'adb.exe')

    logging.info('Stopping Android emulator')
    subprocess.run([adb_path, 'emu', 'kill'])
    logging.info('Emulator stopped')

# Servers

def start_servers(runtime_version, http_port):
    try:
        serverProcess = subprocess.Popen(["node", "servers/servers.js", runtime_version, str(http_port)])
        logging.info(f"Server running on port {http_port}")
        return serverProcess
    except Exception as e:
        logging.error(f"Error starting the server: {e}")
        return None

def stop_servers(serverProcess):
    try:
        serverProcess.terminate()
        logging.info(f"Servers stopped")
    except Exception as e:
        logging.error(f"Error stopping the servers")

# Project Configuration

def project_set_config(data, project_path, ip_address):

    data['Server.ip'] = ip_address

    config_file = os.path.join(project_path, 'datafiles', 'config.json')
    save_to_json_file(data, config_file)

def project_set_sandbox(project_path, platform, active):

    options_file = os.path.join(project_path, 'options', platform, f'options_{platform}.yy')
    data = load_json_file(options_file)
    data[f'option_{platform}_disable_sandbox'] = not active
    save_to_json_file(data, options_file)
    
    config_file = os.path.join(project_path, 'datafiles', 'config.json')
    data = load_json_file(config_file)
    data['$$parameters$$.isSandboxed'] = active
    save_to_json_file(data, config_file)

# Results

def results_update(meta_path, log_path, summary_path):

    metadata = load_json_file(meta_path)

    # Copy log to results folder
    log_dest_path = os.path.join(metadata['folder'], f'{metadata["file"]}.log')
    copy_file(log_path, log_dest_path)

    # Add summary to the results file
    results_path = os.path.join(metadata['folder'], f'{metadata["file"]}.json')

    results = load_json_file(results_path)
    sumary = load_json_file(summary_path)
    results['summary'] = sumary
    save_to_json_file(results, results_path)

def results_create_summary(runtime_version, results_path):
    # Initialize summary dictionary
    summary = {'version': runtime_version, 'results': {}}

    # Loop through all the files in the results directory
    for filename in os.listdir(results_path):
        # Check if the file has a .json extension
        if filename.endswith('.json'):
            # Load the JSON data from the file
            json_data = load_json_file(os.path.join(results_path, filename))

            # Extract the target name from the filename (without extension)
            target_name = os.path.splitext(filename)[0]

            # Determine the target status based on the tallies in the JSON data
            tallies = json_data['data']['tallies']
            if 'failed' in tallies or 'expired' in tallies:
                status = 'FAILED'
            else:
                status = 'PASSED'

            # Removed passed details
            data = json_data['data']
            data['details'].pop('passed', None)

            # Update the summary dictionary with the target status and data
            summary['results'][target_name] = {'status': status, 'data': data}

    # Save the summary dictionary to a JSON file
    summary_path = os.path.join(WORKSPACE_DIR, 'summary.json')
    save_to_json_file(summary, summary_path)

# Execution

def main():

    # Configure logging
    configure_logging()

    # Clean workspace
    remove_directory(USER_DIR)
    remove_directory(WORKSPACE_DIR)

    ensure_directories_exist([ CACHE_DIR, OUTPUT_DIR ])

    # Get arguments
    args = parse_arguments(DEFAULT_CONFIG)

    # Download and extract igor
    download_and_extract(IGOR_URL, IGOR_DIR)
    assert(os.path.exists(IGOR_PATH))

    # Copy user folder locally
    user_folder = copy_folder(args['Launcher.userFolder'], USER_DIR, True)
    assert(os.path.exists(user_folder))

    # Execute igor to get license file
    access_key = args['Launcher.accessKey']
    license_path = os.path.join(user_folder, 'licence.plist')
    igor_get_license(access_key, license_path)
    assert(os.path.exists(license_path))

    # Exectute igor to get the latest runtime version
    rss_feed = args['Launcher.feed']
    runtime_version = igor_get_runtime_version(user_folder, rss_feed, args['Launcher.runtimeVersion'])
    assert(runtime_version != None)

    # Execute igor to install the requested runtime version
    target_kvs = args['Launcher.targets']
    platforms = list({ key for key, _ in target_kvs })
    runtime_path = igor_install_runtime(user_folder, rss_feed, runtime_version, platforms)
    assert(os.path.exists(runtime_path))

    # Load settings
    settings_path = os.path.join(user_folder, 'local_settings.json')
    settings = load_json_file(settings_path)

    # Prepare for HTML5
    if any(key == 'HTML5' for key, _ in target_kvs):
        
        # Download and install the correct version of ChromeDriver
        driver_path = download_chrome_driver(runtime_path)
        assert(os.path.exists(driver_path))

        # Set custom HTML5 runner (scripts folder)
        html5_runner = args['Launcher.html5Runner']
        if html5_runner:
            html5_runner_path = os.path.abspath(html5_runner)
            settings['machine.Platform Settings.HTML5.runner_path'] = html5_runner_path

    # Prepare the Android emulator
    if any(key == 'android' for key, _ in target_kvs):
        # Retrieve the AndroidSDK path from settings
        android_sdk = settings['machine.Platform Settings.Android.Paths.sdk_location']
        emulator_id = start_android_emulator(android_sdk)
        assert(emulator_id != None)

    # Save 'local_settings.json' to workspace and local user (just to be on the safe side)
    save_to_json_file(settings, settings_path)

    # Get the igor runner path
    igor_path = os.path.join(runtime_path, 'bin', 'igor', 'windows', 'x64', 'igor.exe')
    
    # Get local IP address
    ip_address = get_local_ip_address()
    assert(ip_address != None)
    
    # Configure project
    project_file = os.path.abspath(args['Launcher.project'])
    project_folder = os.path.dirname(project_file)
    project_set_config(args, project_folder, ip_address)

    # Starts the servers
    server_port = args['Server.port']
    servers = start_servers(runtime_version, server_port)
    assert(servers != None)

    # For all except HTML5
    runners = args['Launcher.runners']

    for kv in [(key, value) for key, value in target_kvs if key != 'HTML5']:

        platform = kv[0]
        target = f'{kv[0]}|{kv[1]}'

        # If we are on a desktop platform
        if platform in SANDBOXED_PLATFORMS:
            
            # Run test on target (with sandbox OFF)
            project_set_sandbox(project_folder, platform, False)
            for runner in runners:
                igor_run_tests(igor_path, project_file, user_folder, runtime_path, target, runner)

                # For each test update results according to metadata
                if check_file_exists(META_PATH):
                    results_update(META_PATH, LOG_PATH, RESULTS_PATH)

            # Run test on target (with sandbox ON)
            project_set_sandbox(project_folder, platform, True)

        for runner in runners:
            igor_run_tests(igor_path, project_file, user_folder, runtime_path, target, runner)

            # For each test update results according to metadata
            if check_file_exists(META_PATH):
                results_update(META_PATH, LOG_PATH, RESULTS_PATH)

    # Test for HTML5 (slightly different, there is no VM/YYC)
    for kv in [(key, value) for key, value in target_kvs if key == 'HTML5']:
        target = f'{kv[0]}|{kv[1]}'

        # Run project on HTML5
        igor_run_tests(igor_path, user_folder, runtime_path, f"HTML5|{kv[1]}")

        # For each test update results according to metadata
        results_update(META_PATH, LOG_PATH, RESULTS_PATH)

    # Close Android emulator
    if any(key == 'android' for key, _ in target_kvs):
        android_sdk = settings['machine.Platform Settings.Android.Paths.sdk_location']
        stop_android_emulator(android_sdk)

    # Stop the servers
    stop_servers(servers)

    # Write summary file
    results_path = os.path.join(WORKSPACE_DIR, 'results', 'tests', runtime_version)
    results_create_summary(runtime_version, results_path)

    # Check if we should fail the job
    if (check_file_exists(FAIL_PATH)):
        raise Exception(FAILURE_MESSAGE)

if __name__ == '__main__':
    main()