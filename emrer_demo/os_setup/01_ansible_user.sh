#!/bin/sh
# Sample script.
# Creates a user for ansible. User is added to wheel group, which should
# probably have sudo access to run ansible as root.

# run this script only on master node
instance_json='/mnt/var/lib/info/instance.json'
if [ -f $instance_json ]; then
    cat $instance_json | jq '.isMaster' | grep -i "^true$" > /dev/null
    if [[ $? != 0 ]]; then
        exit 0
    fi
fi

set -e

# make the script execute itself as root if we're another user (like 'hadoop')
if [ `whoami` != root ]; then
    sudo sh $0 "$@"
    exit $?
fi

## CREATE USER SVC_ANSIBLE
username='ansible'
ssh_authorized_key='Insert public key here. Anyone with the corresponding private key will be able to log in.'
ssh_ansible_git_deploy_priv="-----BEGIN RSA PRIVATE KEY-----
FIll in private key. This can be a deployment key from a git
repository that  ansible can use to download the contents of
the repository
-----END RSA PRIVATE KEY-----"

# create ansible user
useradd "${username}" -r -G wheel -m
homedir=$( getent passwd "${username}" | cut -d: -f6 )
# set ssh key for ansible
mkdir "${homedir}/.ssh"
printf "${ssh_authorized_key}" > "${homedir}/.ssh/authorized_keys"
echo "${ssh_ansible_git_deploy_priv}" > "${homedir}/.ssh/ansible_git_deploy_rsa"
chown -R "${username}:" "${homedir}/.ssh"
chmod 700 ${homedir}/.ssh
chmod 600 ${homedir}/.ssh/*
