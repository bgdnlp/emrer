from __future__ import unicode_literals
from __future__ import print_function

from warnings import warn

from shlex import split as sh_split
from os import listdir
from os import path

import boto3
from boto3.s3.transfer import S3Transfer

from awslib import upload_to_s3_rand

def main():
    return


def b3_tags(tags_in):
    """Converts tags to boto3 format

    Receives a dictionary and converts it into the {key:x, value:y}
    format that boto3 requires

    Args:
        tags_in (dict):
            dictionary of tags

    Rerurns:
        list
    """
    if not isinstance(tags_in, list):
        tags_in = [tags_in]
    
    tags_out = []
    for tag in tags_in:
        for tag_key in tag:
            tags_out.append({'Key': tag_key, 'Value': tag[tag_key]})

    return tags_out


def b3_bootstrap(bootstrap_action, s3bucket=None, s3prefix=None, session=None):
    """Converts to boto3 BootstrapAction format

    Receives a bootstrap action as loaded from the configuration file and
    returns a structure fit to be passed to boto3 BootstrapActions list.
    Files will be uploaded to S3 if needed.

    YAML OPTIONS:
    The action can be defined using one of "script", "dir", "s3" or "command".
    If an action has more than one defined only the first one will matter.
    name: string
        Bootstrap action name. If not given, the file name will be used.
    script: string
        Path to local file that will be uploaded to S3 and passed on to boto3.
        Arguments can be passed on inline or through the args key. Inline
        arguments will be inserted before the 'args' ones.
    dir: string
        Path to a local directory that contains scripts to be executed as
        bootstrap actions. For each file the function will call itself with
        the 'dir' key replaced with a 'script' key. The files will be ordered
        alphabetically, case insensitive. Arguments will be passed to every 
        script, if defined.
    s3: string
        Path to script on S3. 's3://' will be added if it's not there.
    command: string
        Path to a file that already exists on the EMR host.

    Args:
        bootstrap_action (list): as read from the config file
        s3bucket (string): if a script/dir was passed, it will be uploaded to
            this bucket, unless overwritten by an action option
        s3prefix (string): prefix to be used for the action name if it has to
            be uploaded to S3. Can be overwritten for each action
        session (boto3.session): session to be used for s3 uploads,
            where needed

    Returns:
        list element(s) to be added to the list of bootstrap actions
    """
    # 'actions' will be returned to the calling function
    actions = None
    if 's3bucket' in bootstrap_action:
        s3bucket = bootstrap_action['s3bucket']
    if 's3prefix' in bootstrap_action:
        s3prefix = bootstrap_action['s3prefix']
    # check that one and only one action is defined
    action_count = 0
    if 'script' in bootstrap_action:
        action_count = action_count + 1
    if 'dir' in bootstrap_action:
        action_count = action_count + 1
    if 's3' in bootstrap_action:
        action_count = action_count + 1
    if 'command' in bootstrap_action:
        action_count = action_count + 1
    if action_count != 1:
        # TODO: improve message to point out exactly which action is borked
        raise KeyError('One and only one bootstrap action must be defined')
    # parse the action depending on type
    if 'script' in bootstrap_action:
        # upload the script to S3 and return the path
        actions = []
        action_args = []
        script_line = sh_split(bootstrap_action['script'])
        if len(script_line) == 0:
            # no script_line defined, return an empty dictionary
            warn('"script" type action has no script set. Ignoring it')
            return []
        else:
            script = script_line[0]
            action_args = script_line[1:] + action_args
        if not s3bucket:
            # script defined, but we don't know where to upload it
            raise KeyError('Bucket undefined for script ' + script)

        name_on_s3 = bootstrap_action.get('name_on_s3', '_filename_')
        if name_on_s3.lower() == '_random_':
            action_path = upload_to_s3_rand(session, script,
                    s3bucket, s3prefix)
        elif name_on_s3.lower() in [
                '_script_', '_scriptname_', '_file_', '_filename_'
                ]:
            # TODO: this is a hack to avoid writing another upload function\
            # or changing the current one. fix this hack
            s3prefix = s3prefix + path.basename(script)
            action_path = upload_to_s3_rand(session, script,
                    s3bucket, s3prefix, rand_length=0)
        else:
            # TODO: this is a hack to avoid writing another upload function\
            # or changing the current one. fix this hack
            s3prefix = s3prefix + name_on_s3
            action_path = upload_to_s3_rand(session, script,
                    s3bucket, s3prefix, rand_length=0)

        if not 's3://' in action_path:
            action_path = '{}{}'.format('s3://', action_path)

        if 'args' in bootstrap_action:
            if isinstance(bootstrap_action['args'], str):
                conf_args = sh_split(bootstrap_action['args'])
            else:
                conf_args = bootstrap_action['args']
            action_args.extend(conf_args)

        if 'name' in bootstrap_action:
            action_name = bootstrap_action['name']
        else:
            action_name = bootstrap_action['script'].replace(' ', '_')

        actions = [
            {
                'Name': action_name,
                'ScriptBootstrapAction': {
                    'Path': action_path,
                    'Args': action_args
                }
            }
        ]

        # TODO: this will remove the action before it was executed on all
        # nodes. to be fixed
        if bootstrap_action.get('cleanup'):
            actions.extend([
                {
                    'Name': '{}-cleanup'.format(action_name),
                    'ScriptBootstrapAction': {
                        'Path': 'file://aws',
                        'Args': ['s3', 'rm', action_path]
                    }
                }
            ])
    elif 'dir' in bootstrap_action:
        # Consider 'dir' as a shortcut for multiple 'script' lines. The 'dir'
        # key will be replaced with a 'script' key having the file path as
        # its value, then the function will call itself passing the resulting 
        # 'script' action type as parameter. The return will be appended to
        # the existing actions list, which will then be returned
        actions = []
        if not bootstrap_action['dir']:
            # directory not defined, ignore this action
            warn('"dir" type action has no directory set. Ignoring it')
            return []
        for entry in sorted(listdir(bootstrap_action['dir']), 
                            key=lambda s: s.lower()):
            if not path.isfile(path.join(bootstrap_action['dir'], entry)) \
                    or entry[0] == '.':
                continue
            script_action = dict(bootstrap_action)
            del script_action['dir']
            script_action['script'] = path.join(bootstrap_action['dir'], entry)
            action = b3_bootstrap(script_action, 
                    s3bucket, s3prefix, session=session)
            actions = actions + action
    elif 's3' in bootstrap_action:
        actions = []
        s3_line = sh_split(bootstrap_action['s3'])
        if len(s3_line) == 0:
            warn('"s3" action has no s3 path set, ignoring it')
            return []
        else:
            action_path = s3_line[0]
            action_args = s3_line[1:] + bootstrap_action.get('args', [])
        if not 's3://' in action_path:
            action_path = '{}{}'.format('s3://', action_path)
        if 'name' in bootstrap_action:
            action_name = bootstrap_action['name']
        else:
            action_name = path.basename(action_path).replace(' ', '_')
        actions = [
            {
                'Name': action_name,
                'ScriptBootstrapAction': {
                    'Path': action_path,
                    'Args': action_args
                }
            }
        ]
    elif 'command' in bootstrap_action:
        actions = []
        cmd_line = sh_split(bootstrap_action['command'])
        if len(cmd_line) == 0:
            warn('"command" action has no command set, ignoring it')
            return []
        else:
            action_path = cmd_line[0]
            action_args = cmd_line[1:] + bootstrap_action.get('args', [])
        if not 'file://' in action_path:
            action_path = '{}{}'.format('file://', action_path)
        if 'name' in bootstrap_action:
            action_name = bootstrap_action['name']
        else:
            action_name = path.basename(action_path).replace(' ', '_')
        actions = [
            {
                'Name': action_name,
                'ScriptBootstrapAction': {
                    'Path': action_path,
                    'Args': action_args
                }
            }
        ]

    return actions
 

def b3_step(yaml_step, s3bucket=None, s3prefix=None, session=None):
    """Converts step to boto3 structure.

    Converts an EMR 'step' from the simplified yaml format to the syntax
    needed to pass a step to boto3 EMR client methods like run_job_flow() or
    add_job_flow_steps(). EMR 4.x only.

    YAML structure:
    The step to be executed will be defined using one of 'exec', 'script', 
    'dir', 's3' or 'command'. For each step, only one of these should be
    defined. The first one encountered will determine the actions taken, the
    rest will be ignored.

    name: string, required
        name of the step. 
    on_failure: string, case insensitive, default is "TERMINATE_CLUSTER"
        what to do if the step fails.
        valid values are (case insensitive):
            - terminate | terminate_cluster | terminate_job_flow
            - cancel | wait | cancel_and_wait
            - continue
    type: string, case insensitive, default is "CUSTOM_JAR"
        what kind of step this is. it can be a custom jar to be executed as-is,
        or it can be a script that will be passed to another application by
        "command-runner.jar". valid values (at the end of 2015) are:
            - custom_jar | custom | jar
            - streaming | hadoop-streaming | hadoop_streaming
            - hive | hive-script | hive_script
            - pig
            - impala
            - spark
            - shell - shell scripts are run using script-runner.jar
        NOT ALL OF THEM ARE IMPLEMENTED
    exec: string
        URI to the script/jar to be executed. Will be passed to boto3 as-is.
    script: string
        Path to local file that will be uploaded to S3 and passed on to boto3.
        Arguments can be passed inline or through the args key. Inline
        arguments will be inserted before the 'args' ones.
    dir: string
        Path to a local directory that contains scripts to be executed as
        steps. For each file the function will call itself with 'dir'
        replaced with 'script'. The files will be ordered alphabetically, 
        case insensitive. Arguments will be passed to every script, if defined.
    s3: string
        Path to script on S3. 's3://' will be added if it's not there.
    command: string
        Path to a file that already exists on the EMR host. Arguments inline
        or as 'args'
    args: list
        arguments to be passed to the step. depending on the step `type` the
        list will be interpreted in different ways (or not)
    main_class: string
        the name of the main class in the specified Java file. if not 
        specified, the JAR file should specify a Main-Class in its manifest 
        file. will pe passed on as-is
    properties: list
        a list of Java properties that are set when the step runs. you can use 
        these properties to pass key value pairs to your main function. will be
        passed on as-is

    Args:
        yaml_step (dict): the step as read from yaml file.
        s3bucket (string): name of the bucket that steps will be upladed to
            if they are local scripts
        s3prefix (string): 'directory' in the bucket
        session (session): an already defined session object for uploading

    Returns:
        a list element that can be added to the list of steps the cluster should
        execute
    """
    # check that we received a dictionary, otherwise raise exception
    if not isinstance(yaml_step, dict):
        raise TypeError('Parameter should be a dict, but we received ', 
                        type(yaml_step))

    # check for keys that we require, raise exception if not provided
    required_keys = ['name', 'type'] # name could be 'auto-completed' later
    missing_keys = []
    for key in required_keys:
        if not key in yaml_step:
            missing_keys.append(key)
    require_one_of = ['exec', 'script', 'dir', 's3', 'command']
    require_one_found = False
    for key in require_one_of:
        if key in yaml_step:
            require_one_found = True
            break
    if not require_one_found:
        missing_keys.append('|'.join(require_one_of))
    if len(missing_keys) != 0:
        raise KeyError('Required data missing for this step: ', missing_keys)

    # if we got passed a local script or directory, we need to upload it to s3
    if 'exec' in yaml_step:
        # leave everything as it is, allow user to specify whatever they want
        pass
    elif 'script' in yaml_step:
        # upload file to S3, create 'exec' key as s3:// path
        # first, check that we received an S3 bucket to upload to
        if 's3bucket' in yaml_step:
            s3bucket = yaml_step['s3bucket']
        if 's3prefix' in yaml_step:
            s3prefix = yaml_step['s3prefix']
        if not s3bucket:
            # script defined, but we don't know where to upload it
            raise KeyError('Bucket undefined for step script ' + script)
        # split 'script' in file and arguments, in case there are any
        script_line = sh_split(yaml_step['script'])
        if len(script_line) == 0:
            # no script_line defined, return an empty dictionary
            warn('"script" type step has no script set. Ignoring it')
            return []
        else:
            script = script_line[0]
            yaml_step['args'] = script_line[1:] + yaml_step.get('args', [])
        # upload to s3
        name_on_s3 = yaml_step.get('name_on_s3', '_random_')
        if name_on_s3.lower() == '_random_':
            step_path = upload_to_s3_rand(session, script,
                    s3bucket, s3prefix)
        elif name_on_s3.lower() in [
                '_script_', '_scriptname_', '_file_', '_filename_'
                ]:
            # TODO: this is a hack to avoid writing another upload function\
            # or changing the current one. fix this hack
            s3prefix = s3prefix + path.basename(script)
            step_path = upload_to_s3_rand(session, script,
                    s3bucket, s3prefix, rand_length=0)
        else:
            # TODO: this is a hack to avoid writing another upload function\
            # or changing the current one. fix this hack
            s3prefix = s3prefix + name_on_s3
            step_path = upload_to_s3_rand(session, script,
                    s3bucket, s3prefix, rand_length=0)
        if not 's3://' in step_path:
            step_path = '{}{}'.format('s3://', step_path)
        # set 'exec' to the new path
        yaml_step['exec'] = step_path
    elif 'dir' in yaml_step:
        # call ourselves for each file in dir, replacing 'dir' with 'script'
        # add the converted step for each file to a list that will be returned
        if not yaml_step['dir']:
            # directory not defined, ignore this action
            warn('"dir" type step has no directory set. Ignoring it')
            return []
        boto_steps = []
        for entry in sorted(listdir(yaml_step['dir']), key=lambda s: s.lower()):
            if not path.isfile(path.join(yaml_step['dir'], entry)) \
                    or entry[0] == '.':
                continue
            script_step = dict(yaml_step)
            del script_step['dir']
            script_step['script'] = path.join(yaml_step['dir'], entry)
            boto_step = b3_step(script_step, 
                    s3bucket, s3prefix, session=session)
            boto_steps.extend(boto_step)
        return boto_steps
    elif 's3' in yaml_step:
        # make sure the path starts with 's3://' and set 'exec' key
        script_line = sh_split(yaml_step['s3'])
        if len(script_line) == 0:
            warn('"s3" type step has no script set. Ignoring it')
            return []
        else:
            script = script_line[0]
            yaml_step['args'] = script_line[1:] + yaml_step.get('args', [])
        if not 's3://' in script:
            script = 's3://' + script
        del yaml_step['s3']
        yaml_step['exec'] = script
    elif 'command' in yaml_step:
        # start path with 'file://' and set 'exec'
        script_line = sh_split(yaml_step['command'])
        if len(script_line) == 0:
            warn('"command" type step has no command set. Ignoring it')
            return []
        else:
            script = script_line[0]
            yaml_step['args'] = script_line[1:] + yaml_step.get('args', [])
        if not 'file://' in script:
            script = 'file://' + script
        del yaml_step['command']
        yaml_step['exec'] = script

    # we have what we need, initialize the dictionary that will be returned
    boto_step = {'Name': yaml_step['name']}

    # by default, terminate cluster on step failure
    if 'on_failure' in yaml_step:
        on_failure = yaml_step['on_failure'].lower()
    else:
        on_failure = 'terminate_cluster'
    if on_failure in ['terminate', 'terminate_cluster', 'terminate_job_flow']:
        action_on_failure = 'TERMINATE_CLUSTER'
    elif on_failure in ['cancel', 'wait', 'cancel_and_wait']:
        action_on_failure = 'CANCEL_AND_WAIT'
    elif on_failure in ['continue']:
        action_on_failure = 'CONTINUE'
    else:
        # this step exists only for the warning
        warn('The value "{0}" for on_failure in step "{1}" is not valid. It '
                'will be set to "TERMINATE_CLUSTER".'
                ''.format(on_failure, yaml_step['name']))
        action_on_failure = 'TERMINATE_CLUSTER'
    boto_step['ActionOnFailure'] = action_on_failure

    if 'type' in yaml_step:
        step_type = yaml_step['type'].lower()
    else: # type is required above, but might be optional in the future
        step_type = 'custom'
    # set jar and arguments according to 'type'
    # TODO: mostly incomplete, check
    # https://github.com/aws/aws-cli/blob/develop/awscli/customizations/emr/steputils.py
    # for more info on how to deal with the different types.
    # Or, go to console, create cluster, advanced options, add a step,
    # configure it, then look into the 'arguments' column for hints
    if step_type in ['custom', 'custom_jar', 'custom-jar', 'jar']:
        jar = yaml_step['exec']
        args = yaml_step['args']
    elif step_type in ['streaming', 'hadoop-streaming', 'hadoop_streaming']:
        # TODO: incomplete
        jar = 'command-runner.jar'
        args = [ 'hadoop-streaming' ]
        raise NotImplementedError(step_type)
    elif step_type in ['hive', 'hive-script', 'hive_script']:
        jar = 'command-runner.jar'
        print(yaml_step['exec'])
        args = [
                'hive-script', '--run-hive-script', '--args',
                '-f', yaml_step['exec']
        ]
        for arg in yaml_step['args']:
            if not isinstance(arg, dict) or len(arg) != 1:
                warn('Expected a single key:value pair as argument in step '
                        '{0}. Received {1}, {2}. Ignoring it.'.format(
                        yaml_step['name'], arg, type(arg)))
                continue
            if 'input' in arg:
                args.extend(['-d', 'INPUT=' + arg['input']])
            elif 'output' in arg:
                args.extend(['-d', 'OUTPUT=' + arg['output']])
            elif 'other' in arg:
                args.append(arg['other'])
            else:
                warn("Received argument {0} in step {1}. Don't know what to "
                        'do with it, Ignoring.'.format(arg, yaml_step['name']))
    elif step_type in ['shell', 'shellscript', 'sh']:
        jar = 's3://elasticmapreduce/libs/script-runner/script-runner.jar'
        # 'exec' is string, make it list
        args = [yaml_step['exec']] + yaml_step['args']
    else:
        raise NotImplementedError('Received type {0} in step {1}. This type is '
            'either invalid, or not yet implemented. Use "CUSTOM_JAR" or '
            'contact the programmers.'.format(step_type, yaml_step['name']))

    hadoop_jar_step = {'Jar': jar, 'Args': args}

    if 'main_class' in yaml_step:
        hadoop_jar_step['MainClass'] = yaml_step['main_class']

    if 'properties' in yaml_step:
        hadoop_jar_step['Properties'] = yaml_step['properties']
    
    boto_step['HadoopJarStep'] = hadoop_jar_step

    return [boto_step] # list


def b3_config(config):
    """Convert configuration to boto3
    Convert a configuration element to JSON format to be passed to boto3. The
    element received might already be in JSON format in some cases (file, dir)

    YAML structure:
    A configuration can be read from a file, a directory, or it can be
    specified directly in the config file in YAML
    - file: string
        configuration will be loaded from the specified file and added to the
        current list. File format has to be JSON. Maybe we can automatically
        detect the format later and convert to JSON if needed.
    - dir: string
        directory containing configuration files. The function will call
        itself for each file in the directory, executing the case for 'file'
    - anything else: yaml
        the list element will be converted to JSON and passed to boto3 as-is

    Args:
        config (dict): list element to be passed to boto3

    Returns:
        list of configurations in JSON format
    """
    from json import load as json_load

    # TODO: check that we're getting a dictionary. MAYBE, if we're getting a
    # list we could recursively call this function
    configs = []
    if 'file' in config:
        with open(config['file'], 'r') as f:
           cfg = json_load(f)
        # could check that cfg is either a list or a dictionary here, but we'll
        # just let boto3 deal with it, hoping it does it better than us
        if isinstance(cfg, list):
            configs.extend(cfg)
        else:
            configs.append(cfg)
    elif 'dir' in config:
        # TODO: take subdirectories into account. or not
        for entry in sorted(listdir(config['dir']), key=lambda s: s.lower()):
            file_path = path.join(config['dir'], entry)
            if not path.isfile(file_path) \
                    or entry[0] == '.':
                continue
            cfg = {'file': file_path}
            configs.extend(b3_config(cfg))
    else:
        # nothing to do here, really. just return whatever was received
        configs.append(config) 

    return configs


if __name__ == "__main__":
    # execute only if run as a script
    main()
