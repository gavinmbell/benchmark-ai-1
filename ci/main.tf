terraform {
  required_version = ">= 0.12"

  backend "s3" {
    key    = "ci/terraform.tfstate"
  }
}

provider "aws" {
  version = ">= 2.12.0"
  region  = var.region
}

data "aws_caller_identity" "current" {}

# Generic role for both CodeBuild / CodePipeline to access the S3 bucket with artifacts
resource "aws_s3_bucket" "build-artifacts" {
  bucket = "bai-build-artifacts-${data.aws_caller_identity.current.account_id}"
  acl    = "private"
}

resource "aws_iam_policy" "build-artifacts" {
  name = "bai-build-artifacts"
  description = "Provides permissions for CodePipeline/CodeBuild to start builds and store artifacts"

  policy = <<-EOF
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect":"Allow",
        "Action": [
          "s3:*"
        ],
        "Resource": [
          "${aws_s3_bucket.build-artifacts.arn}",
          "${aws_s3_bucket.build-artifacts.arn}/*"
        ]
      }
    ]
  }
  EOF
}


resource "aws_iam_role" "code-build-role" {
  name = "code-build-role"

  assume_role_policy = <<-EOF
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "codebuild.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }
  EOF
}

resource "aws_iam_role_policy" "code-build-role-policy-logs-permissions" {
  name = "logs-permissions"
  role = aws_iam_role.code-build-role.name

  policy = <<-EOF
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Resource": [
          "*"
        ],
        "Action": [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
      }
    ]
  }
  EOF
}

resource "aws_iam_role_policy" "code-build-role-policy-eks-all-actions" {
  name = "eks-all-actions"
  role = aws_iam_role.code-build-role.name

  policy = <<-EOF
  {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "eks:ListClusters",
                "eks:CreateCluster"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "eks:*",
            "Resource": "arn:aws:eks:${var.region}:${data.aws_caller_identity.current.account_id}:cluster/benchmark-cluster"
        }
    ]
  }
  EOF
}

resource "aws_iam_role_policy_attachment" "build-artifacts" {
  role = aws_iam_role.code-build-role.name
  policy_arn = aws_iam_policy.build-artifacts.arn
}

resource "aws_iam_role_policy_attachment" "ecr-permissions" {
  role = aws_iam_role.code-build-role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

#############################
# CodeBuild project for PRs #
#############################

locals {
  is_official_ci_account = data.aws_caller_identity.current.account_id == "563267192464"
}

resource "aws_codebuild_project" "ci-unit-tests" {
  # Only add PR CodeBuild projects to the official CI account, otherwise it will create webhooks in the official repo.
  # We don't want that for 2 reasons:
  # - Github has a limit of 20 webhooks in a repo.
  # - We don't want other people's instantiations of CI validating PRs to the main repo
  count         = local.is_official_ci_account ? length(var.projects) : 0
  name          = var.projects[count.index]
  description   = "Unit tests build of ${var.projects[count.index]}"
  build_timeout = "30"
  service_role  = aws_iam_role.code-build-role.arn
  badge_enabled = true

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type = "BUILD_GENERAL1_LARGE"
    image = lookup(
      var.ci_docker_image,
      var.projects[count.index],
      var.ci_docker_image["default"]
    )
    type = "LINUX_CONTAINER"
    privileged_mode = true
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/MXNetEdge/benchmark-ai.git"
    git_clone_depth = 1
    auth {
      type = "OAUTH"
    }
    buildspec           = "${var.projects[count.index]}/buildspec.yml"
    report_build_status = true
  }
}

resource "aws_codebuild_webhook" "ci-unit-tests" {
  count        = length(aws_codebuild_project.ci-unit-tests)
  project_name = aws_codebuild_project.ci-unit-tests.*.name[count.index]

  filter_group {
    filter {
      type = "EVENT"
      pattern = "PULL_REQUEST_CREATED, PULL_REQUEST_UPDATED, PULL_REQUEST_REOPENED"
    }
  }
}
