import { describe, expect, it } from 'vitest';
import * as oldIndex from './index';
import { ProjectsPage } from './ProjectsPage';
import { ProjectDetailsPage } from './ProjectDetailsPage';
import { ProjectsProvider, useProjects } from './ProjectsContext';
import * as projectsModule from '../../modules/projects';

// pages/projects/ keeps only re-exports of src/modules/projects (modularization P1B). Every old
// entry point must hand out the module's own objects, so a context provided through one path is
// the same context read through the other.
describe('pages/projects re-exports the Projects module', () => {
  it('gives the same objects through every old entry point', () => {
    expect(ProjectsPage).toBe(projectsModule.ProjectsPage);
    expect(ProjectDetailsPage).toBe(projectsModule.ProjectDetailsPage);
    expect(ProjectsProvider).toBe(projectsModule.ProjectsProvider);
    expect(useProjects).toBe(projectsModule.useProjects);
    expect(oldIndex.ProjectsPage).toBe(projectsModule.ProjectsPage);
    expect(oldIndex.ProjectDetailsPage).toBe(projectsModule.ProjectDetailsPage);
    expect(oldIndex.ProjectsProvider).toBe(projectsModule.ProjectsProvider);
    expect(oldIndex.useProjects).toBe(projectsModule.useProjects);
  });
});
