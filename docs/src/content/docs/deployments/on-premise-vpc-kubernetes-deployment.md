---
title: On-Premise/VPC Kubernetes Deployment
description: Mundi can be deployed on-prem or in a virtual private cloud as a Kubernetes cluster with our Helm charts
---

On-prem Mundi is an extension of open source Mundi that's designed for use with frontier LLMs,
multi-user authentication (SSO/SAML), and is highly available to entire teams simultaneously.

The vast majority of our users are best using Mundi cloud, which is our most advanced
and feature-complete offering, or
[open source Mundi](https://github.com/buntinglabs/mundi.ai), which is free, self-hostable, and
open source (AGPLv3). We recommend on-prem Mundi only for large
organizations or organizations with sensitive data requirements.

:::note
Deployment configurations for Mundi can change over time. For the most up-to-date
information, [schedule a call](https://cal.com/buntinglabs/30min) with us.
:::

## Data privacy

Mundi was designed from the ground up to be deployed on-prem.

Many of our customers operate within strict regulatory frameworks (GDPR, CCPA, SOC 2)
and could benefit from Mundi's ability to run on-premise. This is true both for self-hosted
[open source Mundi](https://github.com/buntinglabs/mundi.ai) and for on-prem Mundi cloud.

By controlling the entire deployment, organizations can independently verify that
data never leaves their network. Self-hosted Mundi can be zero access; giving log access
to the Bunting Labs team is not required.

### GDPR

Organizations subject to GDPR or other European Union data protection laws can
choose to self-host Mundi in EU data centers. Because the entire deployment is
customizable, you can also ensure that LLM/AI model requests are only routed
inside the EU. This makes Mundi a viable option for organizations with EU-centric
data privacy requirements.

## Deployment configuration

We use a Kubernetes environment provisioned by [Helm charts](https://helm.sh/).

On-prem Mundi can be deployed either as cloud-hosted or self-managed. For
cloud-hosted configurations, the [Bunting Labs team](https://buntinglabs.com/)
can optionally manage the Mundi Kubernetes
cluster in your VPC. This allows us to deploy updates as needed.

An organization's IT team can also self-manage the Kubernetes environment,
working closely with our engineering team to work through any issues in a
privacy-preserving manner.

Because Mundi is open source, organizations can always switch between
[self-hosting open source Mundi](/deployments/self-hosting-mundi/) and running
Mundi on-prem in a VPC.

### Compatible cloud providers

We run Mundi cloud on
[Google Kubernetes Engine (GKE)](https://cloud.google.com/kubernetes-engine). However, Mundi is
compatible with AWS's Elastic Kubernetes Service (EKS), Microsoft's Azure Kubernetes Service (AKS),
and other providers with dedicated Kubernetes support.

For small on-prem deployments, it may be possible to use Docker Compose, depending on the usage profile.
For most scenarios with concurrent users, we recommend using Kubernetes.

### FedRAMP High deployment

:::note
Bunting Labs is not FedRAMP Authorized. Instead, Mundi can run on FedRAMP authorized clouds.
:::

Mundi can be deployed to federal users, even though we are not FedRAMP authorized. Because Bunting Labs is not FedRAMP authorized, deploying Mundi requires an on-premises deployment in a FedRAMP authorized cloud. 

**Amazon AWS GovCloud:** Mundi can run on AWS Elastic Kubernetes Service in GovCloud. Amazon Bedrock provides access to LLMs within GovCloud, ensuring that traffic never leaves GovCloud.

**Microsoft Azure Government:** Mundi can run on Azure Kubernetes Service in Azure Government and connect to Azure OpenAI, which is also FedRAMP High. 

### LLM / AI model requirements

Using more powerful LLM models in Mundi improves the user experience.
The most powerful LLMs are called *frontier models* and represent
the best the AI labs have to offer. Frontier models are closed weights and only
available via API.

For organizations with data privacy requirements, there are two main options:
privacy agreements with LLM providers and self-hosting local LLMs.

**Privacy agreements with LLM providers**: Many AI providers, including OpenAI,
Anthropic, AWS, Microsoft Azure, and Google Gemini will agree to a
*Zero Data Retention* agreement with the right organizations. If your organization
has negotiated an agreement with an LLM provider you want to use with Mundi,
on-prem Mundi is compatible with any Chat Completions-compatible API.
[AWS Bedrock](https://aws.amazon.com/bedrock/) is frequently used.

**Local LLMs**: For organizations that would prefer the data never leaves
their managed cluster, it is possible to run open-weights models like Google's Gemma,
Meta's Llama, and DeepSeek. This requires GPUs to be added to the deployment for
reasonable performance.

### Estimating cloud costs

Unlike Mundi cloud, on-prem Mundi customers are responsible for their compute costs.
To help better understand what self-hosting Mundi would cost, we can provide an estimate
of cloud costs. This estimate is based on:

- the number of users
- data profile (raster/vector, size of data, databases)
- LLM models of choice (frontier models range dramatically in cost)
- cloud provider of choice


### Implementation timeline

Mundi cloud deployed on Kubernetes is ready and currently deployed in production on
major cloud providers. The typical deployment timeframe is 1-2 weeks from authorization
to first users.

## Service-level agreements / support

SLAs are available for VPC environments we manage, while self-managed deployments
can have a response time SLA.

Support can be provided over email, Slack, Microsoft Teams, and Zoom. Engineering site visits
are also available depending on location and availability.
