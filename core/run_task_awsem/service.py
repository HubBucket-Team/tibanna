# -*- coding: utf-8 -*-

from core import ec2_utils
from core.utils import powerup, check_dependency
import os


def metadata_only(event):
    event.update({'jobid': 'metadata_only'})
    return event


@powerup('run_task_awsem', metadata_only)
def handler(event, context):
    '''
    config:
    # required
      instance_type: EC2 instance type
      ebs_size: EBS storage size in GB
      ebs_type: EBS storage type (available values: gp2, io1, st1, sc1, standard (default: io1)
      ebs_iops: EBS storage IOPS
      password: password for ssh connection for user ec2-user
      EBS_optimized: Use this flag if the instance type is EBS-optimized (default: EBS-optimized)
      shutdown_min: Number of minutes before shutdown after the jobs are finished. (default now)
      log_bucket: bucket for collecting logs (started, postrun, success, error, log)
    # optional
      public_postrun_json (optional): whether postrun json should be made public (default false)
      cloudwatch_dashboard (optional) : create a cloudwatch dashboard named awsem-<jobid>

    args:
    # required (i.e. field must exist):
      input_files: input files in json format (parametername: {'bucket_name':bucketname, 'object_key':filename})
      output_S3_bucket: bucket name and subdirectory for output files and logs
    # optional
      app_name: name of the app, used by Benchmark
      app_version: version of the app
      secondary_files: secondary files in json format (parametername: {'bucket_name':bucketnname, 'object_ke':filename})
      input_parameters: input parameters in json format (parametername:value)
      secondary_output_target: secondary output files in json format (similar to secondary_files)
    # required for cwl
      cwl_main_filename: main cwl file name
      cwl_directory_url: the url and subdirectories for the main cwl file
      cwl_version: the version of cwl (either 'draft3' or 'v1')
      cwl_child_filenames (optional): names of the other cwl files used by main cwl file, delimited by comma
      language (optional for cwl): 'cwl_v1' or 'cwl_draft3'
    # required for wdl
      language: 'wdl'
      wdl_main_filename: main wdl file name
      wdl_directory_url: the url of the wdl file
      wdl_child_filenames (optional): names of the other wdl files used by main wdl file, delimited by comma
    # optional
      dependency: {'exec_arn': [exec_arns]}
      spot_duration: 60  # block minutes 60-360 if requesting spot instance
    '''

    # read default variables in config
    CONFIG_FIELD = "config"
    CONFIG_KEYS = ["log_bucket"]
    ARGS_FIELD = "args"
    ARGS_KEYS = ["input_files", "output_S3_bucket", "output_target"]
    ARGS_KEYS_CWL = ["cwl_main_filename", "cwl_directory_url"]
    ARGS_KEYS_WDL = ["wdl_main_filename", "wdl_directory_url", "language"]

    # args: parameters needed by the instance to run a workflow
    # cfg: parameters needed to launch an instance
    cfg = event.get(CONFIG_FIELD)
    for k in CONFIG_KEYS:
        assert k in cfg, "%s not in config_field" % k

    args = event.get(ARGS_FIELD)
    for k in ARGS_KEYS:
        assert k in args, "%s not in args field" % k
    if 'language' in args and args['language'] == 'wdl':
        for k in ARGS_KEYS_WDL:
            assert k in args, "%s not in args field" % k
    else:
        for k in ARGS_KEYS_CWL:
            assert k in args, "%s not in args field" % k

    if 'dependency' in args:
        check_dependency(**args['dependency'])

    # update input json to add various other info automatically
    ec2_utils.auto_update_input_json(args, cfg)

    # create json and copy to s3
    jobid = ec2_utils.create_json(event)

    # profile
    if os.environ.get('TIBANNA_PROFILE_ACCESS_KEY', None) and \
            os.environ.get('TIBANNA_PROFILE_SECRET_KEY', None):
        profile = {'access_key': os.environ.get('TIBANNA_PROFILE_ACCESS_KEY'),
                   'secret_key': os.environ.get('TIBANNA_PROFILE_SECRET_KEY')}
    else:
        profile = None

    # launch instance and execute workflow
    launch_instance_log = ec2_utils.launch_instance(cfg, jobid, profile=profile)

    # setup cloudwatch dashboard
    if 'cloudwatch_dashboard' in cfg and cfg['cloudwatch_dashboard']:
        instance_id = launch_instance_log['instance_id']
        ec2_utils.create_cloudwatch_dashboard(instance_id, 'awsem-' + jobid)

    if 'jobid' not in event:
        event.update({'jobid': jobid})
    event.update(launch_instance_log)
    return(event)
