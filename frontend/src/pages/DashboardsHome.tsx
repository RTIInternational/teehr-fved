import { Container, Row, Col, Card, Button } from 'react-bootstrap';
import { Link } from 'react-router-dom';

import { DASHBOARD_NAV_ITEMS, type DashboardNavigationItem } from '@/config/dashboardNavigation';

const DashboardsHome = () => {
  const dashboards = DASHBOARD_NAV_ITEMS;

  const getCardComponent = (dashboard: DashboardNavigationItem) => {
    if (dashboard.status === 'available') {
      return (
        <Link to={dashboard.route} style={{ textDecoration: 'none' }}>
          <Card
            className="h-100 dashboard-card dashboard-card-available"
            style={{ cursor: 'pointer' }}
          >
            <Card.Header className={`bg-${dashboard.color} text-white`}>
              <Card.Title className="mb-0">{dashboard.label}</Card.Title>
            </Card.Header>
            <Card.Body className="d-flex flex-column">
              <Card.Text>{dashboard.description}</Card.Text>
              <div className="features-list mb-3">
                <strong>Features:</strong>
                <ul className="mt-2">
                  {dashboard.features.map((feature, idx) => (
                    <li key={idx}>{feature}</li>
                  ))}
                </ul>
              </div>
              <div className="mt-auto">
                <Button variant={dashboard.color} className="w-100">
                  Open Dashboard
                </Button>
              </div>
            </Card.Body>
          </Card>
        </Link>
      );
    } else {
      return (
        <Card className="h-100 dashboard-card dashboard-card-disabled">
          <Card.Header className={`bg-${dashboard.color} text-white opacity-75`}>
            <Card.Title className="mb-0">
              {dashboard.label}
              <span className="badge bg-warning text-dark ms-2">Coming Soon</span>
            </Card.Title>
          </Card.Header>
          <Card.Body className="d-flex flex-column">
            <Card.Text className="text-muted">{dashboard.description}</Card.Text>
            <div className="features-list mb-3">
              <strong className="text-muted">Planned Features:</strong>
              <ul className="mt-2 text-muted">
                {dashboard.features.map((feature, idx) => (
                  <li key={idx}>{feature}</li>
                ))}
              </ul>
            </div>
            <div className="mt-auto">
              <Button variant="outline-secondary" disabled className="w-100">
                Coming Soon
              </Button>
            </div>
          </Card.Body>
        </Card>
      );
    }
  };

  return (
    <div className="home-page bg-preset-hydro">
      {/* Hero Section */}
      <div className="hero-section bg-primary text-white py-5 mb-4">
        <Container>
          <Row className="justify-content-center text-center">
            <Col lg={8}>
              <h1 className="display-4 mb-3">TEEHR Dashboard Hub</h1>
              <p className="lead">
                Tools for Exploratory Evaluation in Hydrologic Research. Choose from our collection
                of specialized dashboards for hydrologic data analysis.
              </p>
            </Col>
          </Row>
        </Container>
      </div>

      {/* Dashboard Cards */}
      <Container>
        <Row className="mb-4">
          <Col>
            <h2 className="text-center mb-4">Available Dashboards</h2>
          </Col>
        </Row>
        <Row className="g-4">
          {dashboards.map((dashboard) => (
            <Col key={dashboard.id} lg={4} md={6} sm={12}>
              {getCardComponent(dashboard)}
            </Col>
          ))}
        </Row>

        {/* Footer Info */}
        <Row className="mt-5 pt-4">
          <Col className="text-center text-muted">
            <p>
              <strong>TEEHR</strong> - Tools for Exploratory Evaluation in Hydrologic Research.
            </p>
          </Col>
        </Row>
      </Container>
    </div>
  );
};

export default DashboardsHome;
