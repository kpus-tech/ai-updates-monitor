#!/usr/bin/env python3
"""CDK Application entry point for AI Updates Monitor."""

import aws_cdk as cdk
from stacks.ai_updates_stack import AiUpdatesStack

app = cdk.App()

AiUpdatesStack(
    app,
    "AiUpdatesMonitor",
    description="AI/ML Updates Monitor - polls sources and notifies on changes",
)

app.synth()
