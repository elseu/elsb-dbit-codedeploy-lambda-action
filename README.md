# Deploy a lambda function with CodeDeploy

This action will:
 - update an AWS Lamda function code with the provided package
 - create a function version
 - get the version currently associated with the provided alias
 - trigger AWS Code Deploy to publish the new version 
 
 ## Usage
 
```yaml
  jobs:
    deploy:
     runs-on: ubuntu-latest
     steps:
       - uses: elseu/elsb-dbit-codedeploy-lambda-action@v1
         with:
           app_name: <Code Deploy application name>
           deployment_group: <Code Deploy deployment group>
           package_s3_bucket: <S3 bucket hosting the application package>
           package_s3_key: <Package S3 key (full path)>
           function_name: <Lambda function name or ARN>
           alias: <Alias to associate with the published version>
```