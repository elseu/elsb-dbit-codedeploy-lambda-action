import os
import boto3
import hashlib

lambda_svc = boto3.client('lambda')
code_deploy_svc = boto3.client('codedeploy')
new_layers_list = []
current_layers_list = []
needs_deployment = False


def get_latest_version_number(my_function_name, sha256, already_published=False):
    latest_version = None
    versions = []
    layers_list = []

    try:
        paginator = lambda_svc.get_paginator('list_versions_by_function')
        page_iterator = paginator.paginate(FunctionName=my_function_name)
        for page in page_iterator:
            versions = versions + page["Versions"]

    except lambda_svc.exceptions.ClientError as e:
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
            latest_version = version_id
            layers_list = get_layers_list(publish_version_response["Layers"])
        except lambda_svc.exceptions.ClientError as e:
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
                if "Layers" in version:
                    layers_list = get_layers_list(version["Layers"])
        if last_matching_version:
            print("Last matching version: " + last_matching_version)
            latest_version = last_matching_version
        else:
            # The current $LATEST version has never been published. Publishing it.

            # As it's a recursive call to the same function, we need to avoid loop
            if not already_published:
                try:
                    lambda_svc.publish_version(FunctionName=my_function_name)
                    latest_version, layers_list = get_latest_version_number(my_function_name, sha256, True)
                except lambda_svc.exceptions.ClientError as e:
                    raise e

    return latest_version, layers_list


def get_layers_list(layer_configuration):
    layer_list = []
    for layer in layer_configuration:
        layer_list.append(layer["Arn"])
    return layer_list


def get_env_var(var_name, required):
    if var_name in os.environ:
        return os.environ[var_name]
    else:
        if required is True:
            raise RuntimeError("Required parameter " + var_name + " missing.")
        return None


# Getting the input parameters
input_alias = get_env_var('INPUT_ALIAS', True)
app_name = get_env_var('INPUT_APP_NAME', True)
deployment_group = get_env_var('INPUT_DEPLOYMENT_GROUP', True)
package_s3_bucket = get_env_var('INPUT_PACKAGE_S3_BUCKET', True)
package_s3_key = get_env_var('INPUT_PACKAGE_S3_KEY', True)
function_name = get_env_var('INPUT_FUNCTION_NAME', True)
layer1_arn = get_env_var('INPUT_LAYER1_ARN', False)
layer2_arn = get_env_var('INPUT_LAYER2_ARN', False)
layer3_arn = get_env_var('INPUT_LAYER3_ARN', False)
layer4_arn = get_env_var('INPUT_LAYER4_ARN', False)


# CodeDeploy needs a function alias. Checking if the alias passed as input parameter exists and get the
# version currently associated to it. If not existing, create it.
print("Getting the current version associated to the alias + CodeSha256")

current_function_version = None
current_function_sha256 = None

try:
    alias_response = lambda_svc.get_alias(
        FunctionName=function_name,
        Name=input_alias
    )
    current_function_version = alias_response['FunctionVersion']
    current_configuration_response = lambda_svc.get_function_configuration(FunctionName=function_name,
                                                                           Qualifier=current_function_version)
    current_function_sha256 = current_configuration_response['CodeSha256']
    if "Layers" in current_configuration_response:
        current_layers_list = get_layers_list(current_configuration_response["Layers"])

except lambda_svc.exceptions.ClientError as error:
    # The requested alias doesn't exists yet
    if error.response['Error']['Code'] == 'ResourceNotFoundException':

        # To create an alias associated to the current version, we need the current version number

        try:
            config_response = lambda_svc.get_function_configuration(FunctionName=function_name)
            current_function_version = config_response['Version']
            current_function_sha256 = config_response['CodeSha256']
        except lambda_svc.exceptions.ClientError as error:
            raise error

        if current_function_version == "$LATEST":
            current_function_version, current_layers_list = get_latest_version_number(function_name,
                                                                                      current_function_sha256)
            if current_function_version is None:
                raise RuntimeError("Unable to get an existing numeric version")
        try:
            create_alias_response = lambda_svc.create_alias(
                FunctionName=function_name,
                Name=input_alias,
                FunctionVersion=current_function_version
            )
        except lambda_svc.exceptions.ClientError as error:
            raise error

    else:
        raise error

print("Current version: " + current_function_version)
print("Current SHA256: " + current_function_sha256)

new_function_sha256 = None
new_function_version = None

print("Updating the function code")
try:
    update_response = lambda_svc.update_function_code(
        FunctionName=function_name,
        S3Bucket=package_s3_bucket,
        S3Key=package_s3_key,
        Publish=True
    )
    update_status = update_response["LastUpdateStatus"]
    if update_status == "Failed":
        raise RuntimeError("Function update failed: " + update_status)

except lambda_svc.exceptions.ClientError as error:
    raise error
new_function_sha256 = update_response["CodeSha256"]
new_function_version = update_response["Version"]

print("New version: " + new_function_version)
print("New SHA256: " + new_function_sha256)

if current_function_version != new_function_version:
    needs_deployment = True

print("Checking the function layers")
# Manage layers

if layer1_arn != "":
    new_layers_list.append(layer1_arn)
if layer2_arn != "":
    new_layers_list.append(layer2_arn)
if layer3_arn != "":
    new_layers_list.append(layer3_arn)
if layer4_arn != "":
    new_layers_list.append(layer4_arn)

print("Previous layers list: " + ','.join(current_layers_list))
print("New layers list: " + ','.join(new_layers_list))

# The lists order is important
if current_layers_list != new_layers_list:
    needs_deployment = True
    # Update function configuration
    print("Updating the function layers")
    try:
        update_response = lambda_svc.update_function_configuration(FunctionName=function_name, Layers=new_layers_list)
        update_status = update_response["LastUpdateStatus"]
        if update_status == "Failed":
            raise RuntimeError("Function update failed: " + update_status)
        else:
            new_function_version, new_layers_list = get_latest_version_number(function_name,
                                                                              update_response["CodeSha256"])
            print("New version: " + new_function_version)

    except lambda_svc.exceptions.ClientError as error:
        raise error

if needs_deployment:
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
    deploy_response = code_deploy_svc.create_deployment(
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
    waiter = code_deploy_svc.get_waiter('deployment_successful')
    waiter.wait(
        deploymentId=deploy_response["deploymentId"],
        WaiterConfig={
            'Delay': 5,
            'MaxAttempts': 20
        }
    )
else:
    print("Same code, nothing to deploy")
