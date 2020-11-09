#!/bin/sh

export APP_NAME=111
export DEPLOYMENT_GROUP=222
export PACKAGE_S3_BUCKET=333
export PACKAGE_S3_KEY=444
export FUNCTION_NAME=555
export ALIAS=666

echo "Updating the function code"
echo "Publishing a new version of the function and getting the new version id"
echo "Getting the version_id currently associated with the given alias"
FUNCTION_ALIAS_VERSION=777
FUNCTION_VERSION=888

echo "Create AppSpec.json"
FILE_CONTENT="{'version': '0.0',
'Resources': [{
  '${FUNCTION_NAME}': {
    'Type': 'AWS::Lambda::Function',
    'Properties': {
      'Name': '${FUNCTION_NAME}',
      'Alias': '${ALIAS}',
      'CurrentVersion': '${FUNCTION_VERSION}',
      'TargetVersion': '${FUNCTION_ALIAS_VERSION}'
    }
  }
}],
'Hooks': []
}"
echo $FILE_CONTENT | sed "s/'/\"/g"
echo $FILE_CONTENT > AppSpec.json
