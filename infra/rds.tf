###############################################################################
# DB Subnet Group — spans both private subnets (required by Aurora)
###############################################################################
resource "aws_db_subnet_group" "main" {
  name        = "${var.app_name}-${var.environment}-db-subnet-group"
  description = "Private subnets for ${var.app_name} ${var.environment} Aurora cluster"
  subnet_ids  = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = {
    Name = "${var.app_name}-${var.environment}-db-subnet-group"
  }
}

###############################################################################
# Aurora Serverless v2 Cluster
#
# Note: Aurora Serverless v2 uses engine_mode = "provisioned" (NOT "serverless")
# combined with a serverlessv2_scaling_configuration block. The cluster instance
# class must be "db.serverless". This is the common gotcha vs. v1.
###############################################################################
resource "aws_rds_cluster" "main" {
  cluster_identifier = "${var.app_name}-${var.environment}-aurora"

  engine         = "aurora-postgresql"
  engine_version = "15.17"
  engine_mode    = "provisioned" # required for Serverless v2

  database_name   = var.db_name
  master_username = var.db_username
  master_password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 8
  }

  # Encrypt storage at rest
  storage_encrypted = true

  # Skip final snapshot on destroy. Defaults to true (dev teardown cycles);
  # set var.skip_final_snapshot = false (with a final_snapshot_identifier) for
  # production so `terraform destroy` captures a snapshot first (issue #181).
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : var.final_snapshot_identifier

  # Prevent accidental destruction of the production database.
  # Set var.deletion_protection = false only when intentionally tearing down.
  deletion_protection = var.deletion_protection

  backup_retention_period = 7
  preferred_backup_window = "03:00-04:00"

  lifecycle {
    # A variable cannot drive the skip_final_snapshot/identifier coupling from a
    # variable-validation block, so enforce it here at plan time: requesting a
    # final snapshot without naming it would otherwise only fail at destroy.
    precondition {
      condition     = var.skip_final_snapshot || (var.final_snapshot_identifier != null && var.final_snapshot_identifier != "")
      error_message = "final_snapshot_identifier must be set (non-empty) when skip_final_snapshot = false, otherwise `terraform destroy` will fail."
    }

    # Strongest plan-time guard for a real production cluster. Terraform does not
    # allow a variable here, so this is a deliberate manual edit before go-live:
    # uncomment to make `terraform destroy` of this cluster impossible until the
    # line is removed again.
    # prevent_destroy = true
  }

  tags = {
    Name = "${var.app_name}-${var.environment}-aurora"
  }
}

###############################################################################
# Aurora Serverless v2 Instance
###############################################################################
resource "aws_rds_cluster_instance" "main" {
  identifier         = "${var.app_name}-${var.environment}-aurora-instance-1"
  cluster_identifier = aws_rds_cluster.main.id

  engine         = aws_rds_cluster.main.engine
  engine_version = aws_rds_cluster.main.engine_version

  instance_class = "db.serverless"

  db_subnet_group_name = aws_db_subnet_group.main.name

  publicly_accessible = false

  tags = {
    Name = "${var.app_name}-${var.environment}-aurora-instance-1"
  }
}
