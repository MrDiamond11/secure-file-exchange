# guardrails.tf
#
# Vive en SU PROPIO state, separado del proyecto (main.tf), para que
# sobreviva aunque destruyas el proyecto. Este es tu "botón de pánico".

data "azurerm_subscription" "current" {}
data "azurerm_client_config" "current" {}

variable "location" {
  default = "swedencentral"
}

# true = la función solo registra qué haría, sin borrar ni cancelar nada.
# Cámbialo a false explícitamente cuando confíes en el comportamiento.
variable "dry_run" {
  default = "true"
}

# Secreto propio para autenticar el webhook — no usamos las claves internas
# de Azure Functions porque Terraform no puede leerlas de forma fiable.
resource "random_password" "guardian_secret" {
  length  = 32
  special = false
}

resource "azurerm_resource_group" "guardrails" {
  name     = "rg-guardrails"
  location = var.location
}

# ---------------------------------------------------------------------------
# Function App que ejecuta el corte (borra resource groups + cancela la sub)
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "guardian" {
  name                     = "stguardianfunc"
  resource_group_name      = azurerm_resource_group.guardrails.name
  location                 = azurerm_resource_group.guardrails.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_service_plan" "guardian" {
  name                = "plan-guardian"
  resource_group_name = azurerm_resource_group.guardrails.name
  location            = azurerm_resource_group.guardrails.location
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption, always free
}

resource "azurerm_linux_function_app" "guardian" {
  name                       = "func-cost-guardian-${substr(data.azurerm_subscription.current.subscription_id, 0, 8)}"
  resource_group_name        = azurerm_resource_group.guardrails.name
  location                   = azurerm_resource_group.guardrails.location
  service_plan_id            = azurerm_service_plan.guardian.id
  storage_account_name       = azurerm_storage_account.guardian.name
  storage_account_access_key = azurerm_storage_account.guardian.primary_access_key

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    SUBSCRIPTION_ID      = data.azurerm_subscription.current.subscription_id
    KEEP_RESOURCE_GROUP  = azurerm_resource_group.guardrails.name
    GUARDIAN_SECRET       = random_password.guardian_secret.result
    DRY_RUN               = var.dry_run
  }
}

# Owner a nivel de suscripción: imprescindible para poder borrar
# cualquier grupo de recursos y cancelar la propia suscripción.
resource "azurerm_role_assignment" "guardian_owner" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Owner"
  principal_id         = azurerm_linux_function_app.guardian.identity[0].principal_id
}

# ---------------------------------------------------------------------------
# Action Group — email + webhook a la Function
# ---------------------------------------------------------------------------
resource "azurerm_monitor_action_group" "cost_guard" {
  name                = "ag-cost-guard"
  resource_group_name = azurerm_resource_group.guardrails.name
  short_name          = "costguard"

  email_receiver {
    name          = "owner-email"
    email_address = var.alert_email
  }

  webhook_receiver {
    name        = "cost-guardian-function"
    service_uri = "https://${azurerm_linux_function_app.guardian.default_hostname}/api/cost-guardian?secret=${random_password.guardian_secret.result}"
  }
}

# ---------------------------------------------------------------------------
# Budget a nivel de SUSCRIPCIÓN (vigila todo, no solo un resource group)
# ---------------------------------------------------------------------------
resource "azurerm_consumption_budget_subscription" "guard" {
  name            = "budget-1eur"
  subscription_id = data.azurerm_subscription.current.id

  amount     = 1
  time_grain = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  # Aviso temprano por email al 50%, para que te enteres antes del corte
  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.cost_guard.id]
  }

  # Al llegar al 100% (1€ real) dispara el webhook -> corte automático
  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.cost_guard.id]
  }
}

variable "alert_email" {
  description = "Email donde llegan los avisos antes del corte automático"
  type        = string
}

output "guardian_function_url" {
  value = "https://${azurerm_linux_function_app.guardian.default_hostname}"
}

output "guardian_secret" {
  value     = random_password.guardian_secret.result
  sensitive = true
}
