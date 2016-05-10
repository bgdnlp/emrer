from random import choice
from string import ascii_uppercase
from datetime import datetime

from boto3.s3.transfer import S3Transfer

def upload_to_s3_rand(session, file_to_upload, s3bucket, 
        prefix=None, postfix=None, rand_length=12):
    """
    Uploads a file to an S3 bucket giving it a randomized name and returns
    that name.

    Args:
        session (boto3.session): 
        file_to_upload (str): hopefully obvious
        s3bucket (str): bucket to upload to
        prefix (str): a string that will be prepended to the random string.
            also serves as a 'path' on S3
        postfix (str): will be appended to the random string
        rand_length (int): length of the random string to be genrated

    Returns:
        name of the S3 object, None if it fails
    """
    rand = ''.join(choice(ascii_uppercase) for i in range(rand_length))
    s3key = '{0}{1}{2}'.format(prefix or '', rand, postfix or '')
    s3c = session.client('s3')
    s3transfer = S3Transfer(s3c)

    s3transfer.upload_file(file_to_upload, s3bucket, s3key)

    return '{}/{}'.format(s3bucket, s3key)


def get_amazon_linux_ami(latest=True):
    """
    A dummy function for now, when developped it should return one and only
    one id of an Amazon Linux AMI to be used. Arguments can be passed on to
    to identify the exact image. 'latest' should return the newest version
    of Amazon Linux, HVM, EBS-Backed, 64-bit (the most used image),
    depending on region.

    Check this page on how to find the Linux AMI:
    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/finding-an-ami.html

    Here's how to filter images from the command line:
    aws --profile bf_edcdev_luputb ec2 describe-images --owners self amazon \
            --filters "Name=root-device-type,Values=ebs" \
                "Name=virtualization-type,Values=hvm" \
                "Name=architecture,Values=x86_64"
    """
    return 'ami-0eac257d'


def get_emr_release_label():
    """
    dummy function
    At some point it will return a release label depnding on passed parameters.
    'latest' should be a valid parameter, probably the default
    """
    return 'emr-4.3.0'

def get_cluster_ids(session, state=None, states=[], 
        created_after=datetime.min, created_before=datetime.max,
        tags_any={}, tags_all={}):
    """Returns a list of clusters that satisfy parameters

    Args:
        state (str): Shortcut for cluster states. Can be either 'on' or 'off'. 
            'on' means ['STARTING','BOOTSTRAPPING','RUNNING','WAITING']
            'off' means ['TERMINATING','TERMINATED','TERMINATED_WITH_ERRORS']
            If defined the states will be appended to the list provided
            in the 'states' parameter if that's also being received.
        states (list): Can be any combination of 'STARTING','BOOTSTRAPPING',
            'RUNNING','WAITING','TERMINATING','TERMINATED' and
            'TERMINATED_WITH_ERRORS'.
        created_after (datetime): self-explanatory
        created_before (datetime): self-eplanatory
        tags_any (dict): If the cluster is tagged with any of these, it 
            will be added to the list.
        tags_all (dict): all tags must exist on the cluster for it to 
            make the cut.

    Returns:
        list of cluster IDs
    """
    cluster_ids = []
    
    if state == 'on':
        states.extend(['STARTING','BOOTSTRAPPING','RUNNING','WAITING'])
    elif state == 'off':
        states.extend(['TERMINATING','TERMINATED','TERMINATED_WITH_ERRORS'])
    else:
        pass 
    
    emr = session.client('emr')
    paginator = emr.get_paginator('list_clusters')
    for page in paginator.paginate(CreatedAfter=created_after, 
            CreatedBefore=created_before,
            ClusterStates=states):
        for cluster in page['Clusters']:
            cluster_ids.append(cluster['Id'])
    # If no other condition was specified, there is no point in going through
    # the whole list looking for nothing. return the list as we have it.
    # WILL NEED TO BE ADJUSTED IF MORE ARGUMENTS ARE ADDED
    # (there's probably a better way, but not going to bother yet)
    if len(tags_any) == 0 and len(tags_all) == 0:
        return cluster_ids
    
    # There are additional filters to apply. Go through the list, describe
    # each cluster and test againist filters. First failure, remove it
    # from the list and move on. 
    # We have to iterate over a copy of the list, otherwise the remove()
    # will cause the loop to jump over clusters
    for cluster_id in list(cluster_ids):
        keep_cluster = False
        cluster = emr.describe_cluster(ClusterId=cluster_id)['Cluster']
        # check tags
        c_tags = cluster['Tags']
        # first, tags_any. first tag found, continue to next filter
        # if no tag found, remove from list and move to next cluster
        if len(tags_any) > 0:
            for c_tag in c_tags:
                if c_tag['Key'] in tags_any.keys() and \
                        c_tag['Value'] == tags_any[c_tag['Key']]:
                    keep_cluster = True
                    break
            if not keep_cluster:
                cluster_ids.remove(cluster_id)
                continue
        # next, tags_all
        keep_cluster = True
        for key in tags_all.keys():
            tag_found = False
            for c_tag in c_tags:
                if c_tag['Key'] == key and c_tag['Value'] == tags_all[key]:
                    tag_found = True
                    break
            if not tag_found:
                keep_cluster = False
                break
        if not keep_cluster:
            cluster_ids.remove(cluster_id)
            continue

    return cluster_ids

