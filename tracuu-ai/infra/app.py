import os

import aws_cdk as cdk

from tracuu.stack import TracuuStack

app = cdk.App()
TracuuStack(app, "Tracuu", env=cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=app.node.try_get_context("region") or os.getenv("CDK_DEFAULT_REGION") or "ap-southeast-1"))
app.synth()
