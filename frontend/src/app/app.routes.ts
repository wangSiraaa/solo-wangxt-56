import { Routes } from '@angular/router';
import { ContractListComponent } from './contract-list.component';
import { ContractDetailComponent } from './contract-detail.component';
import { VersionListComponent } from './version-list.component';
import { VersionDetailComponent } from './version-detail.component';

export const routes: Routes = [
  { path: '', redirectTo: 'contracts', pathMatch: 'full' },
  { path: 'contracts', component: ContractListComponent },
  { path: 'contracts/:id', component: ContractDetailComponent },
  { path: 'versions', component: VersionListComponent },
  { path: 'versions/:id', component: VersionDetailComponent },
];
