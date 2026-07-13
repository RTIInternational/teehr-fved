apiVersion: v1
kind: ConfigMap
metadata:
  name: jupyterhub-profile-list
  namespace: ${environment.namespace}
  labels:
    app: jupyterhub
    component: hub
data:
  profile-list.json: |
    {
      "version": 1,
      "profiles": [
        {
          "display_name": "Forecast Visualization and Evaluation Dashboard (FVED)",
          "default": true,
          "description": "Choose this profile for work related to the FVED Project.",
          "profile_options": {
            "image": {
              "display_name": "Image",
              "choices": {
                "current-tag-xlarge": {
                  "display_name": "Version ${var.stableTeehrVersion} - XL (4 cores, 16 GB memory)",
                  "kubespawner_override": {
                    "image": "${actions.build.teehr-jupyter-driver-image-stable.outputs.deploymentImageId}",
                    "mem_limit": "32G",
                    "mem_guarantee": "19G",
                    "cpu_limit": 4,
                    "cpu_guarantee": 3,
                    "node_selector": {
                      "teehr-hub/nodegroup-name": "nb-r5-xlarge"
                    }
                  },
                  "default": true
                },
                "current-tag-4xlarge": {
                  "display_name": "Version ${var.stableTeehrVersion} - 4XL (16 cores, 128 GB memory)",
                  "kubespawner_override": {
                    "image": "${actions.build.teehr-jupyter-driver-image-stable.outputs.deploymentImageId}",
                    "mem_limit": "127G",
                    "mem_guarantee": "76G",
                    "cpu_limit": 15.5,
                    "cpu_guarantee": 12,
                    "node_selector": {
                      "teehr-hub/nodegroup-name": "nb-r5-4xlarge"
                    }
                  }
                },
                "previous-tag-xlarge": {
                  "display_name": "Version ${var.previousTeehrVersion} - XL (4 cores, 32 GB memory)",
                  "kubespawner_override": {
                    "image": "${actions.build.teehr-jupyter-driver-image-previous.outputs.deploymentImageId}",
                    "mem_limit": "32G",
                    "mem_guarantee": "19G",
                    "cpu_limit": 4,
                    "cpu_guarantee": 3,
                    "node_selector": {
                      "teehr-hub/nodegroup-name": "nb-r5-xlarge"
                    }
                  }
                },
                "previous-tag-4xlarge": {
                  "display_name": "Version ${var.previousTeehrVersion} - 4XL (16 cores, 128 GB memory)",
                  "kubespawner_override": {
                    "image": "${actions.build.teehr-jupyter-driver-image-previous.outputs.deploymentImageId}",
                    "mem_limit": "128G",
                    "mem_guarantee": "76G",
                    "cpu_limit": 16,
                    "cpu_guarantee": 12,
                    "node_selector": {
                      "teehr-hub/nodegroup-name": "nb-r5-4xlarge"
                    }
                  }
                },
                "dev-xlarge": {
                  "display_name": "Bleeding Edge ${slice(var.devTeehrVersion, 0, 6)} - XL (4 cores, 32 GB memory)",
                  "kubespawner_override": {
                    "image": "${actions.build.teehr-jupyter-driver-image-edge.outputs.deploymentImageId}",
                    "mem_limit": "32G",
                    "mem_guarantee": "19G",
                    "cpu_limit": 4,
                    "cpu_guarantee": 3,
                    "node_selector": {
                      "teehr-hub/nodegroup-name": "nb-r5-xlarge"
                    }
                  }
                },
                "dev-4xlarge": {
                  "display_name": "Bleeding Edge ${slice(var.devTeehrVersion, 0, 6)} - 4XL (16 cores, 128 GB memory)",
                  "kubespawner_override": {
                    "image": "${actions.build.teehr-jupyter-driver-image-edge.outputs.deploymentImageId}",
                    "mem_limit": "127G",
                    "mem_guarantee": "76G",
                    "cpu_limit": 15.5,
                    "cpu_guarantee": 12,
                    "node_selector": {
                      "teehr-hub/nodegroup-name": "nb-r5-4xlarge"
                    }
                  }
                }
              }
            }
          },
          "kubespawner_override": {
            "environment": {
              "TEEHR_PROJECT_ID": "FVED"
            }
          }
        }
      ]
    }
