from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    core
)

import boto3
import dateutil.parser
import os

# Simplistic way to manage some secrets via the environment
# from the developer's laptop/workstation.
PROFILE = os.environ['AWS_PROFILE']
KEY_NAME = os.environ['AWS_KEY_NAME']
try:
    AWS_PREFIX_LIST = os.environ['AWS_PREFIX_LIST']
except:
    AWS_PREFIX_LIST = None
AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
AWS_SESSION_TOKEN = os.environ['AWS_SESSION_TOKEN']

REGIONS = ['ap-southeast-1']
UBUNTU = 'ubuntu'
CENTOS = 'centos'
AL2 = 'AL2'


AMI_FILTERS = {
    'ubuntu': { 'Owner': '099720109477',
                'name': 'ubuntu/images/hvm-ssd/ubuntu-focal*'
              },
    'centos': { 'Owner': '125523088429',
                'name': 'CentOS 8*aarch64'
              },
    'AL2': { 'Owner': '137112412989',
             'name': 'amzn2-ami-hvm*gp2'}
}

def getLatestAmi(arch: str, name_filter: str, owner: str):
    ami_map = {}
    for region in REGIONS:
        session = boto3.session.Session(profile_name=PROFILE, region_name=region, 
                        aws_access_key_id=AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                        aws_session_token=AWS_SESSION_TOKEN)
        client = session.client("ec2")
        resp = client.describe_images(ExecutableUsers=["all"],
            Filters=[{'Name': 'architecture', 'Values': [arch]},
                     {'Name': 'name', 'Values': [name_filter]}],
            Owners=[owner]
            )
        images = resp["Images"]
        images = sorted(images, key=lambda image: dateutil.parser.parse(image['CreationDate']))
        ami_map[region] = images[0]['ImageId']

    return ec2.MachineImage.generic_linux(ami_map)


def getLatestUbuntuAmi():
    return getLatestAmi('arm64', AMI_FILTERS[UBUNTU]['name'], AMI_FILTERS[UBUNTU]['Owner'])


def getLatestAL2Ami():
    return getLatestAmi('arm64', AMI_FILTERS[AL2]['name'], AMI_FILTERS[AL2]['Owner'])


def getLatestCentosAmi():
    return getLatestAmi('arm64', AMI_FILTERS[CENTOS]['name'], AMI_FILTERS[CENTOS]['Owner'])


class Arm64WheelTesterStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # The code that defines your stack goes here
        # Just do it ugly straight line for now
        vpc = ec2.Vpc(self, "Github-Selfhost-vpc",
                      nat_gateways = 0,
                      enable_dns_hostnames = True,
                      enable_dns_support = True,
                      subnet_configuration=[ec2.SubnetConfiguration(name="selfhost_public", subnet_type=ec2.SubnetType.PUBLIC)]
                      )

        # AMI
        # al2 = getLatestAL2Ami()
        # centos = getLatestCentosAmi()
        ubuntu = getLatestUbuntuAmi()

        instances = []

        # Instance creation.
        # Stands up an instance, then installs the github runner on the first boot.
        # This can be made into a loop. TODO
        user_data_focal = ec2.UserData.for_linux()
        user_data_focal.add_commands("apt-get update -y",
                                     "apt-get upgrade -y",
                                     "apt-get install -y curl software-properties-common",
                                     "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -",
                                     "add-apt-repository "
                                     "'deb [arch=arm64] https://download.docker.com/linux/ubuntu focal stable'",
                                     "apt-get update -y",
                                     "apt-get install -y docker-ce docker-ce-cli containerd.io",
                                     "systemctl start docker")
        instance_focal1 = ec2.Instance(self, "focal1-tester",
            instance_type=ec2.InstanceType("m6g.large"),
            machine_image=ubuntu,
            vpc=vpc,
            key_name=KEY_NAME,
            block_devices=[ec2.BlockDevice(device_name='/dev/sda1', volume=ec2.BlockDeviceVolume(ec2.EbsDeviceProps(volume_size=128)))],
            user_data=user_data_focal)
        instances.append(instance_focal1)

        # Allow inbound HTTPS connections
        for instance in instances:
            instance.connections.allow_from_any_ipv4(ec2.Port.tcp(443), 'Allow inbound HTTPS connections')
            if AWS_PREFIX_LIST:
                instance.connections.allow_from(ec2.Peer.prefix_list(AWS_PREFIX_LIST), ec2.Port.tcp(22), 'Allow inbound SSH connections from trusted sources')
