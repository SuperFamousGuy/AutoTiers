###############################################################################
# ALB Security Group — accepts HTTP (80) and HTTPS (443) from the internet.
###############################################################################
resource "aws_security_group" "alb" {
  name        = "${var.app_name}-${var.environment}-sg-alb"
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
