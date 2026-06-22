###############################################################################
# ALB Security Group — accepts HTTP (80) and HTTPS (443) from the internet.
#
# Zero-downtime replacement (issue #411): this SG is internet-facing and is
# referenced by aws_lb.main and by aws_security_group.ecs's ingress rule, so a
# destroy-before-create replacement drops/disrupts prod traffic while the new SG
# is built. Two coupled settings make any replacement safe:
#
#   - create_before_destroy = true — Terraform creates the new SG, repoints the
#     ALB and the ECS ingress at it, and only then destroys the old one. Traffic
#     is never without a SG.
#   - name_prefix instead of name — create_before_destroy is impossible with a
#     fixed `name`: AWS rejects the second SG with InvalidGroup.Duplicate before
#     the old one is gone. name_prefix lets AWS mint a unique GroupName for the
#     replacement so the old and new can coexist during the swap. The stable,
#     human-readable identifier lives in the Name tag (unchanged), so the console
#     and any tag-based lookups are unaffected.
#
# See docs/runbooks/terraform-state-reconcile.md for the maintenance-window
# procedure this enables.
###############################################################################
resource "aws_security_group" "alb" {
  name_prefix = "${var.app_name}-${var.environment}-sg-alb-"
  description = "Allow HTTP and HTTPS inbound to the ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.app_name}-${var.environment}-sg-alb"
  }

  lifecycle {
    create_before_destroy = true
  }
}

###############################################################################
# ECS Security Group — accepts port 8000 only from the ALB SG
###############################################################################
resource "aws_security_group" "ecs" {
  name        = "${var.app_name}-${var.environment}-sg-ecs"
  description = "Allow inbound traffic from the ALB to the ECS tasks on port 8000"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Backend API from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Allow all outbound (internet via NAT, RDS, Secrets Manager)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.app_name}-${var.environment}-sg-ecs"
  }
}

###############################################################################
# RDS Security Group — accepts Postgres (5432) only from the ECS SG
###############################################################################
resource "aws_security_group" "rds" {
  name        = "${var.app_name}-${var.environment}-sg-rds"
  description = "Allow PostgreSQL inbound from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.app_name}-${var.environment}-sg-rds"
  }
}
