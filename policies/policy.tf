# policy.tf
#
# Se aplica UNA SOLA VEZ a nivel de suscripción, fuera del ciclo de vida
# del proyecto (no se destruye con `terraform destroy` del main.tf).
# Requiere rol "Resource Policy Contributor" u "Owner" en la suscripción.

data "azurerm_subscription" "current" {}

# ---------------------------------------------------------------------------
# 1. Bloquea por completo los tipos de recurso caros que este proyecto
#    no necesita (VMs, SQL, AKS, Synapse, Databricks, App Gateway...)
# ---------------------------------------------------------------------------
resource "azurerm_subscription_policy_assignment" "deny_expensive_types" {
  name                 = "deny-expensive-resource-types"
  display_name         = "Bloquear tipos de recurso caros"
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/6c112d4e-5bc7-47ae-a041-ea2d9dccd749" # Built-in: "Not allowed resource types"
  subscription_id      = data.azurerm_subscription.current.id

  parameters = jsonencode({
    listOfResourceTypesNotAllowed = {
      value = [
        "Microsoft.Compute/virtualMachines",
        "Microsoft.Compute/virtualMachineScaleSets",
        "Microsoft.Sql/servers",
        "Microsoft.DBforPostgreSQL/servers",
        "Microsoft.DBforMySQL/servers",
        "Microsoft.ContainerService/managedClusters",
        "Microsoft.Network/applicationGateways",
        "Microsoft.Network/azureFirewalls",
        "Microsoft.Cdn/profiles",
        "Microsoft.Synapse/workspaces",
        "Microsoft.Databricks/workspaces",
        "Microsoft.HDInsight/clusters"
      ]
    }
  })
}

# ---------------------------------------------------------------------------
# 2. Si algún día sí necesitas una VM puntual, limita el SKU al always-free
#    (Standard_B1s en la promo de 12 meses, o el más barato disponible)
# ---------------------------------------------------------------------------
resource "azurerm_subscription_policy_assignment" "allowed_vm_skus" {
  name                 = "allowed-vm-skus"
  display_name         = "Solo permitir VM Standard_B1s"
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/cccc23c7-8427-4f53-ad12-b6a63eb452b3" # Built-in: "Allowed virtual machine size SKUs"
  subscription_id      = data.azurerm_subscription.current.id

  parameters = jsonencode({
    listOfAllowedSKUs = {
      value = ["Standard_B1s"]
    }
  })
}

# ---------------------------------------------------------------------------
# 3. Fuerza a que cualquier Storage Account sea el tier barato (LRS),
#    nunca Premium ni GRS/ZRS (más caros)
# ---------------------------------------------------------------------------
resource "azurerm_subscription_policy_assignment" "allowed_storage_skus" {
  name                 = "allowed-storage-skus"
  display_name         = "Solo permitir Storage Standard_LRS"
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/7433c107-6db4-4ad1-b57a-a76dce0154a1" # Built-in: "Allowed storage account SKUs"
  subscription_id      = data.azurerm_subscription.current.id

  parameters = jsonencode({
    listOfAllowedSKUs = {
      value = ["Standard_LRS"]
    }
  })
}

# ---------------------------------------------------------------------------
# 4. Restringe las regiones permitidas (evita que algo se despliegue en
#    una región cara o que no esperabas)
# ---------------------------------------------------------------------------
resource "azurerm_subscription_policy_assignment" "allowed_locations" {
  name                 = "allowed-locations"
  display_name         = "Regiones permitidas (prueba de cuota)"
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c" # Built-in: "Allowed locations"
  subscription_id      = data.azurerm_subscription.current.id

  parameters = jsonencode({
    listOfAllowedLocations = {
      value = ["westeurope", "northeurope", "swedencentral", "uksouth", "eastus2", "centralus", "westus2"]
    }
  })
}
