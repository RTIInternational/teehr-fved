import { Accordion, Anchor, Container, Group, List, Paper, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

import teehrCloudServicesDiagram from '@/assets/cloud-services-image.png';
import teehrDashboardsDiagram from '@/assets/dashboard-snippet-image.png';
import teehrIcebergDiagram from '@/assets/data-model-iceberg.png';
import teehrCloudVennDiagram from '@/assets/teehr-cloud-venn-diagram.png';

import styles from './Home.module.css';

const DASHBOARDS_URL = 'https://dashboards.teehr.rtiamanzi.org/';
const GITHUB_MARK = 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png';
const TEEHR_README_IMAGES = 'https://github.com/RTIInternational/teehr/blob/main/docs/images/readme';

const TEEHR_PYTHON_FEATURES = [
  {
    image: `${TEEHR_README_IMAGES}/fetching-and-loading.png?raw=true`,
    title: 'Fetching and Loading',
    description:
      'Tools to bring external or local data into your Evaluation from a variety of sources and file formats.',
  },
  {
    image: `${TEEHR_README_IMAGES}/data-validation-and-storage.png?raw=true`,
    title: 'Data Validation and Storage',
    description:
      "TEEHR's data model helps ensure consistency in field values and types, and interfaces with Apache Iceberg for underlying data storage functionality.",
  },
  {
    image: `${TEEHR_README_IMAGES}/analytics.png?raw=true`,
    title: 'Analytics',
    description:
      'TEEHR contains a suite of robust and scalable analytic methods that enable users to fully interrogate their datasets.',
  },
];

/** External link that opens in a new tab. */
const ExternalLink = ({ href, children }: { href: string; children: ReactNode }) => (
  <Anchor href={href} target="_blank" rel="noreferrer">
    {children}
  </Anchor>
);

/** External link led by a small logo, e.g. GitHub or the TEEHR favicon. */
const IconLink = ({
  href,
  icon,
  iconAlt,
  label,
}: {
  href: string;
  icon: string;
  iconAlt: string;
  label: string;
}) => (
  <Anchor href={href} target="_blank" rel="noreferrer" className={styles.iconLink}>
    <img src={icon} alt={iconAlt} width={20} height={20} />
    <span>{label}</span>
  </Anchor>
);

const Home = () => {
  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <Container size="md">
          <Title order={1} className={styles.heroTitle}>
            Welcome to TEEHR-Cloud
          </Title>
          <Text className={styles.heroLead}>
            Facilitating continental-scale evaluation of historical and real-time hydrologic data.
          </Text>
        </Container>
      </header>

      <Container size="md" py={{ base: 'lg', md: 'xl' }}>
        <Paper radius="md" p={{ base: 'lg', md: 'xl' }} className={styles.card}>
          <Title order={3} c="usbrBlue.9" mb="sm">
            The TEEHR-Cloud Framework
          </Title>
          <Text c="dimmed" mb="lg">
            TEEHR-Cloud (Tools for Exploratory Evaluation in Hydrologic Research) is a cloud-based
            Evaluation Platform that supports standardized evaluations and provides
            “evaluation-ready” datasets, dashboards, and analytics capabilities.
          </Text>

          <Accordion variant="contained">
            <Accordion.Item value="overview">
              <Accordion.Control>Overview</Accordion.Control>
              <Accordion.Panel>
                <Text>
                  The framework combines the TEEHR-Python package, cloud infrastructure, and
                  user-facing tools to support end-to-end evaluation workflows. This includes
                  transforming heterogeneous data sources into consistent schemas, enabling
                  reproducible analysis, and delivering results through notebooks and dashboards.
                </Text>
                <img
                  src={teehrCloudVennDiagram}
                  alt="TEEHR-Cloud Venn diagram"
                  className={`${styles.diagram} ${styles.overviewDiagram}`}
                />
              </Accordion.Panel>
            </Accordion.Item>

            <Accordion.Item value="teehr-python">
              <Accordion.Control>TEEHR-Python Package</Accordion.Control>
              <Accordion.Panel>
                <Text mb="md">
                  The TEEHR-Python package provides the core functionality for data processing,
                  analysis, and evaluation. It includes modules for fetching USGS and National Water
                  Model data from external sources, downloading data from the TEEHR data warehouse,
                  validating and loading data into a local or remote warehouse, and performing
                  advanced analytics at scale by leveraging Apache Spark's distributed computing
                  frameworks.
                </Text>
                <div className={styles.features}>
                  {TEEHR_PYTHON_FEATURES.map(({ image, title, description }) => (
                    <Group key={title} wrap="nowrap" gap="md" className={styles.feature}>
                      <img src={image} alt={title} className={styles.featureImage} />
                      <Text>
                        <strong>{title}</strong> - {description}
                      </Text>
                    </Group>
                  ))}
                </div>
                <Stack gap="xs" mt="md" align="flex-start">
                  <IconLink
                    href="https://rtiinternational.github.io/teehr"
                    icon="/favicon.png"
                    iconAlt="TEEHR logo"
                    label="TEEHR-Python Documentation"
                  />
                  <IconLink
                    href="https://github.com/RTIInternational/teehr"
                    icon={GITHUB_MARK}
                    iconAlt="GitHub logo"
                    label="TEEHR-Python on GitHub"
                  />
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>

            <Accordion.Item value="data-warehouse">
              <Accordion.Control>Data Warehouse</Accordion.Control>
              <Accordion.Panel>
                <Text>
                  The TEEHR data warehouse is the core data layer for model, observation, and derived
                  "Evaluation-Ready" products. Built on Apache Iceberg, it enables scalable storage,
                  query performance for continental datasets, and standardized access patterns used
                  across notebooks, services, and dashboards.
                </Text>
                <img
                  src={teehrIcebergDiagram}
                  alt="TEEHR Data Warehouse Diagram"
                  className={styles.diagram}
                />
                <Text>
                  The warehouse contains an ever-expanding list of historical and real-time
                  hydrologic datasets including, but not limited to:
                </Text>
                <List my="sm" spacing={4}>
                  <List.Item>
                    The National Water Model (NWM) v3.0 hourly retrospective streamflow and
                    accompanying USGS gage observations at over 8,000 gage locations across the US
                  </List.Item>
                  <List.Item>
                    The National Water Model (NWM) v3.0 hourly retrospective rainfall and
                    temperature summarized to USGS drainage basins across the US
                  </List.Item>
                  <List.Item>Historical research simulations</List.Item>
                  <List.Item>
                    CIROH's{' '}
                    <ExternalLink href="https://hub.ciroh.org/blog/nextgen-research-datastream-april-2026/">
                      Nextgen Research Datastream forecasts
                    </ExternalLink>
                  </List.Item>
                  <List.Item>
                    <ExternalLink href="https://water.noaa.gov/">
                      National Water Prediction Service (NWPS)
                    </ExternalLink>{' '}
                    River Forecast Center streamflow forecasts
                  </List.Item>
                  <List.Item>
                    NWM v3.0 analysis, short-range, and medium-range streamflow forecasts for CONUS
                    and OCONUS locations in near real-time
                  </List.Item>
                  <List.Item>
                    NWM v3.0 analysis, short-range, and medium-range streamflow rainrate forecasts
                    summarized to CONUS and OCONUS USGS drainage basins in near real-time
                  </List.Item>
                </List>
                <Text>
                  In addition to simulated and observed hydrologic data, the warehouse also contains
                  tables storing historical and regularly-updated performance metrics and other
                  tables supporting the <ExternalLink href={DASHBOARDS_URL}>TEEHR Dashboards</ExternalLink>.
                </Text>
              </Accordion.Panel>
            </Accordion.Item>

            <Accordion.Item value="services">
              <Accordion.Control>Services and Evaluation Manager</Accordion.Control>
              <Accordion.Panel>
                <Text>
                  A suite of cloud-based services regularly ingests data, updates performance
                  metrics, supports data warehouse access and notebook-based interactions, and hosts
                  the <ExternalLink href={DASHBOARDS_URL}>TEEHR Dashboards</ExternalLink>.
                </Text>
                <img
                  src={teehrCloudServicesDiagram}
                  alt="TEEHR Cloud Services Diagram"
                  className={styles.diagram}
                />
                <IconLink
                  href="https://github.com/RTIInternational/teehr-hub"
                  icon={GITHUB_MARK}
                  iconAlt="GitHub logo"
                  label="TEEHR-Cloud Infrastructure on GitHub"
                />
              </Accordion.Panel>
            </Accordion.Item>

            <Accordion.Item value="dashboards">
              <Accordion.Control>TEEHR Dashboards</Accordion.Control>
              <Accordion.Panel>
                <Text>
                  Purpose-built <ExternalLink href={DASHBOARDS_URL}>dashboards</ExternalLink>{' '}
                  deliver interactive performance visualizations and data exploration tools to
                  support evaluation of historical simulations and real-time forecasts from specific
                  perspectives and use-cases.
                </Text>
                <img
                  src={teehrDashboardsDiagram}
                  alt="TEEHR Dashboards Diagram"
                  className={styles.diagram}
                />
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </Paper>

        <Group wrap="nowrap" gap="lg" p="md" mt="xl" className={styles.funding}>
          <img
            src={`${TEEHR_README_IMAGES}/CIROHLogo_200x200.png?raw=true`}
            alt="CIROH logo"
            className={styles.fundingLogo}
          />
          <Text>
            Funding for this project was provided by the National Oceanic & Atmospheric
            Administration (NOAA), awarded to the Cooperative Institute for Research to Operations in
            Hydrology (CIROH) through the NOAA Cooperative Agreement with The University of Alabama
            (NA22NWS4320003).
          </Text>
        </Group>

        <Text ta="center" c="dimmed" mt={48}>
          <strong>TEEHR</strong> - Tools for Exploratory Evaluation in Hydrologic Research.
        </Text>
      </Container>
    </div>
  );
};

export default Home;
