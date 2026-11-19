import { Container } from '@mantine/core';
import { Outlet } from 'react-router-dom';

const AdminLayout = () => {
  return (
    <Container fluid py="lg">
      <Outlet />
    </Container>
  );
};

export default AdminLayout;
