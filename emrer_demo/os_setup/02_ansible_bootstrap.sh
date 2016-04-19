#!/bin/sh

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

## INSTALL ANSIBLE LOCALLY AND RUN ANSIBLE-PULL FOR INITIAL HOST SETUP
printf "I am G`whoami`\n"
username='ansible'
homedir=$( getent passwd "${username}" | cut -d: -f6 )
ansible_pkg_dir="/tmp/ansible.pip"
ansible_git_dir="/tmp/bootstrapAnsibleRepo"
ansible_install_dir="/tmp/ansible"
ansible_git_url="git@ansible.git:ansible.emr.bootstrap.git"
ansible_s3_path="$1"

# get the AWS account id from the instance metadata
# depending on the account, we'll set the environment (dev/prod)
aws_account=`curl --silent \
    http://169.254.169.254//latest/dynamic/instance-identity/document/ \
    | grep accountId | awk -F '"' '{print $4}'`
case $aws_account in
    "111111111111") envtype="dev";;
    "222222222222") envtype="prod";;
    *) envtype="unknown";;
esac
init_playbook="aws${envtype}.yml"
init_inventory="${ansible_git_dir}/inventory/aws${envtype}.yml"
printf "Determined that we are running in $envtype environment\n"

# install git. needed for ansible-pull
printf "Installing git\n"
yum install -y git

# get pip packages from bucket
mkdir ${ansible_pkg_dir}
cd ${ansible_pkg_dir}
printf "Downloading ansible packages from ${ansible_s3_path} in `pwd`... "
aws s3 cp --recursive s3://${ansible_s3_path} ./
printf "done\n"
printf "Installing ansible... "
PYTHONUSERBASE="${ansible_install_dir}" pip install ansible --user --no-index --find-links ${ansible_pkg_dir}
printf "done\n"
PATH=${ansible_install_dir}/bin:$PATH
printf "Setting vault password... "
echo "ThereIsNoVault" > ${ansible_git_dir}Wault
printf "done\n"
# this is just an example, ansible won't actually be executed
# in a real world, though, here's how it would work
ansible_command="
PYTHONUSERBASE=${ansible_install_dir} ${ansible_install_dir}/bin/ansible-pull --accept-host-key \
    --directory=${ansible_git_dir} \
    --inventory-file=${init_inventory} \
    --key-file=${homedir}/.ssh/ansible_git_deploy_rsa \
    --url=$ansible_git_url \
    --vault-password-file=${ansible_git_dir}Wault \
    ${init_playbook}
"
printf "Not running $ansible_command... done\n"
