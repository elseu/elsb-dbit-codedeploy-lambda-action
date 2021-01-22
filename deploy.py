import os
import botocore
import boto3
import hashlib

# Getting the input parameters
app_name = os.environ['INPUT_APP_NAME']
deployment_group = os.environ['INPUT_DEPLOYMENT_GROUP']
packages_s3_bucket = os.environ['INPUT_PACKAGE_S3_BUCKET']
packages_s3_key = os.environ['INPUT_PACKAGE_S3_KEY']
function_name = os.environ['INPUT_FUNCTION_NAME']
input_alias = os.environ['INPUT_ALIAS']

lambda_svc = boto3.client('lambda')
s3_svc = boto3.client('s3')
codedeploy_svc = boto3.client('codedeploy')

def get_latest_version_number(my_function_name, sha256):
    try:
        versions_response = lambda_svc.list_versions_by_function(FunctionName=my_function_name)
        versions = versions_response["Versions"]
    except botocore.exceptions.ClientError as e:
        raise e

    if len(versions) == 1:
        # Only one version (LATEST) available, need to publish a new one
        print("No numeric version, will publish a new one. ")
        try:
            publish_version_response = lambda_svc.publish_version(FunctionName=my_function_name)
            version_id = publish_version_response["Version"]
            # Unfortunately, returns $LATEST instead of 1. Should list again so value fixed const
            if version_id == "$LATEST":
                version_id = 1
            #version_arn = publish_version_response["FunctionArn"] + ":1"
            #return version_arn
            return version_id
        except botocore.exceptions.ClientError as e:
            raise e
    else:
        # We need to compare sha256 values to get the last one with this value.
        last_matching_version = None
        for version in versions:
            if version["Version"] == "$LATEST":
                continue
            if version["CodeSha256"] == sha256:
                last_matching_version = version["Version"]
                print("Found matching version: " + version["Version"])
        if last_matching_version:
            print("Last matching version: " + last_matching_version)
            return last_matching_version
        else:
            return None


# CodeDeploy needs a function alias. Checking if the alias passed as input parameter exists and get the
# version currently associated to it. If not existing, create it.
print("Getting the current version associated to the alias + CodeSha256")

current_function_version = current_function_sha256 = None

try:
    alias_response = lambda_svc.get_alias(
        FunctionName=function_name,
        Name=input_alias
    )
    current_function_version = alias_response['FunctionVersion']
    current_configuration_response = lambda_svc.get_function_configuration(FunctionName=function_name, Qualifier=current_function_version)
    current_function_sha256 = current_configuration_response['CodeSha256']

except botocore.exceptions.ClientError as error:
    # The requested alias doesn't exists yet
    if error.response['Error']['Code'] == 'ResourceNotFoundException':

        # To create an alias associated to the current version, we need the current version number

        try:
            config_response = lambda_svc.get_function_configuration(FunctionName=function_name)
            current_function_version = config_response['Version']
            current_function_sha256 = config_response['CodeSha256']
        except botocore.exceptions.ClientError as error:
            raise error

        if current_function_version == "$LATEST":
            current_function_version = get_latest_version_number(function_name, current_function_sha256)
            if current_function_version is None:
                raise RuntimeError("Unable to get an existing numeric version")
        try:
            create_alias_response = lambda_svc.create_alias(
                FunctionName=function_name,
                Name=input_alias,
                FunctionVersion=current_function_version
            )
        except botocore.exceptions.ClientError as error:
            raise error

    else:
        raise error

print("Current version: " + current_function_version)
print("Current SHA256: " + current_function_sha256)

new_function_sha256 = new_function_version = None

print("Updating the function code")
try:
    update_response = lambda_svc.update_function_code(
        FunctionName=function_name,
        S3Bucket=packages_s3_bucket,
        S3Key=packages_s3_key,
        Publish=True
    )
    update_status = update_response["LastUpdateStatus"]
    if update_status == "Failed":
        raise RuntimeError("Function update failed: " + update_status)

except botocore.exceptions.ClientError as error:
    raise error
new_function_sha256 = update_response["CodeSha256"]
new_function_version = update_response["Version"]

print("New version: " + new_function_version)
print("New SHA256: " + new_function_sha256)

if current_function_version != new_function_version:
    # Deploy the new version with code deploy
    print("Deploying the new version")

    file_content = """
    {'version': '0.0',
        'Resources': [{
          '""" + function_name + """': {
            'Type': 'AWS::Lambda::Function',
            'Properties': {
              'Name': '""" + function_name + """',
              'Alias': '""" + input_alias + """',
              'CurrentVersion': """ + current_function_version + """,
              'TargetVersion': """ + new_function_version + """
            }
          }
        }]
    }"""
    deploy_response = codedeploy_svc.create_deployment(
        applicationName=app_name,
        deploymentGroupName=deployment_group,
        revision={
            'revisionType': 'AppSpecContent',
            'appSpecContent': {
                'content': file_content,
                'sha256': hashlib.sha256(file_content.encode()).hexdigest()
            }
        }
    )
    print("Deployment ID: " + deploy_response["deploymentId"])
    waiter = codedeploy_svc.get_waiter('deployment_successful')
    waiter.wait(
        deploymentId=deploy_response["deploymentId"],
        WaiterConfig={
            'Delay': 5,
            'MaxAttempts': 20
        }
    )
else:
    print("Same code, nothing to deploy")