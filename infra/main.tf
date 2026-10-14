terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.47"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "azuread" {}

data "azurerm_client_config" "current" {}

variable "project" {
  default = "file-exchange"
}

variable "location" {
  default = "swedencentral"
}

# Static Web Apps solo existe en centralus, eastus2, westus2, westeurope y
# eastasia. La región solo afecta al metadato de gestión, no a dónde se sirve.
variable "swa_location" {
  default = "eastus2"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.project}"
  location = var.location
}

# ---------------------------------------------------------------------------
# App Registration — hace de "usuario de servicio" para que la Function
# pueda leer secretos de Key Vault. Necesario porque el tier Free de
# Static Web Apps NO soporta Managed Identity.
# ---------------------------------------------------------------------------
resource "azuread_application" "function_sp" {
  display_name = "sp-${var.project}-function"
}

resource "azuread_service_principal" "function_sp" {
  client_id = azuread_application.function_sp.client_id
}

resource "azuread_application_password" "function_sp" {
  application_id    = azuread_application.function_sp.id
  display_name      = "function-secret"
  end_date_relative = "8760h" # 1 año
}

# ---------------------------------------------------------------------------
# Key Vault — clave privada PGP del "servidor". Solo el App Registration
# de arriba tiene permiso de lectura sobre los secretos.
# ---------------------------------------------------------------------------
resource "azurerm_key_vault" "main" {
  name                       = "kv-${var.project}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = var.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
}

# Permiso para ti (quien despliega) — poder subir/gestionar los secretos
resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
}

# Permiso para la Function (vía el App Registration) — solo lectura
resource "azurerm_key_vault_access_policy" "function" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azuread_service_principal.function_sp.object_id

  secret_permissions = ["Get", "List"]
}

# ---------------------------------------------------------------------------
# Cosmos DB — free tier, 1000 RU/s + 25 GB de por vida. Solo una cuenta
# con free tier por suscripción.
# ---------------------------------------------------------------------------
resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-${var.project}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  free_tier_enabled   = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "files"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  throughput          = 1000
}

resource "azurerm_cosmosdb_sql_container" "files" {
  name                = "encrypted-files"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/id"]
}

# ---------------------------------------------------------------------------
# Static Web App — frontend + Managed Functions API en un único recurso.
# Nivel Free: sin coste por ejecución, sin Storage Account propia que pagar.
# ---------------------------------------------------------------------------
resource "azurerm_static_web_app" "main" {
  name                = "swa-${var.project}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.swa_location
  sku_tier            = "Free"
  sku_size            = "Free"

  app_settings = {
    AZURE_TENANT_ID          = data.azurerm_client_config.current.tenant_id
    AZURE_CLIENT_ID          = azuread_application.function_sp.client_id
    AZURE_CLIENT_SECRET      = azuread_application_password.function_sp.value
    KEYVAULT_URL              = azurerm_key_vault.main.vault_uri
    COSMOS_ENDPOINT           = azurerm_cosmosdb_account.main.endpoint
    COSMOS_CONNECTION_STRING  = azurerm_cosmosdb_account.main.primary_sql_connection_string
  }
}

# ---------------------------------------------------------------------------
# Salidas
# ---------------------------------------------------------------------------
output "static_web_app_url" {
  value = "https://${azurerm_static_web_app.main.default_host_name}"
}

output "static_web_app_deployment_token" {
  value     = azurerm_static_web_app.main.api_key
  sensitive = true
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}
